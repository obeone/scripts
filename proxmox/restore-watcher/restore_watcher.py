"""CLI tool to monitor active Proxmox restore tasks from task logs."""

from __future__ import annotations

import argparse
import collections
import itertools
import math
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import TextIO

# Proxmox worker types for a restore: qmrestore for VMs, vzrestore for LXC
# containers (PVE::API2::LXC::create_vm picks it when restoring).
RESTORE_ACTION_MARKERS = ["qmrestore", "vzrestore"]
RESTORE_KEYWORD_MARKERS = ["restore"]
ACTIVE_STATUS_MARKERS = {"", "0"}

TASKS_LOG_DIR = "/var/log/pve/tasks"
ACTIVE_TASKS_INDEX = "active"
HEX_ARCHIVE_FOLDERS = "0123456789ABCDEF"

# Proxmox renders sizes through PVE::Format::render_bytes, which emits IEC
# units. Longer unit names must come first in the alternation so that "MiB" is
# never truncated to a bare "B" match.
_SIZE_UNIT_ALTERNATION = "KiB|MiB|GiB|TiB|PiB|B"
_SIZE_UNIT_TO_GIB: dict[str, float] = {
    "b": 1 / (1024**3),
    "kib": 1 / (1024**2),
    "mib": 1 / 1024,
    "gib": 1.0,
    "tib": 1024.0,
    "pib": 1024.0**2,
}

# PVE::Format::render_duration joins the largest non-zero units among weeks,
# days, hours, minutes and seconds, e.g. "0s", "3s", "1m 31s", "1d 2h".
_DURATION_PATTERN = r"(?:\d+[wdhms]\s*)+"
_DURATION_UNIT_SECONDS: dict[str, int] = {
    "w": 7 * 24 * 3600,
    "d": 24 * 3600,
    "h": 3600,
    "m": 60,
    "s": 1,
}

_PROGRESS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "size_with_total",
        re.compile(
            r"transferred\s+(?P<transferred>\d+(?:\.\d+)?)\s*"
            rf"(?P<unit>{_SIZE_UNIT_ALTERNATION})\b\s+of\s+"
            r"(?P<total>\d+(?:\.\d+)?)\s*"
            rf"(?P<total_unit>{_SIZE_UNIT_ALTERNATION})\b"
            rf".*?\sin\s+(?P<elapsed>{_DURATION_PATTERN})",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "qmrestore_bytes_progress",
        re.compile(
            r"progress\s+(?P<percent>\d+(?:\.\d+)?)%\s+"
            r"\(read\s+(?P<read_bytes>\d+)\s+bytes,.*?"
            r"duration\s+(?P<duration_seconds>\d+)\s+sec\)",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "percent_only",
        re.compile(
            r"transferred\s+(?P<percent>\d+(?:\.\d+)?)%\s+in\s+"
            rf"(?P<elapsed>{_DURATION_PATTERN})",
            flags=re.IGNORECASE,
        ),
    ),
)
ProgressPoint = tuple[int, float, float | None]
TerminalStatus = str | None

# Only the worker epilogue written by PVE::RESTEnvironment::fork_worker is
# terminal. Matching loose words like "completed" or "success" ended monitoring
# early on innocuous lines, for instance a volume being removed successfully
# midway through a restore.
_SUCCESS_STATUS_MARKERS = ("task ok",)
_FAILURE_STATUS_MARKERS = ("task error",)
# A task finishing with warnings ends on TASK WARNINGS instead of TASK OK, so it
# has to be terminal too or the watcher would wait out the idle timeout on an
# already finished restore.
_WARNING_STATUS_MARKERS = ("task warnings",)
_COLOR_RESET = "\033[0m"
_COLOR_GREEN = "\033[32m"
_COLOR_CYAN = "\033[36m"
_COLOR_YELLOW = "\033[33m"
_COLOR_DIM = "\033[2m"

# Color escapes take no screen columns, so they must be discounted before any
# width computation.
_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

_MIN_BAR_WIDTH = 8
_MAX_BAR_WIDTH = 28
# Highest expendability tag used by the status line segments; see
# build_tqdm_line for the ordering.
_MOST_EXPENDABLE_SEGMENT = 5
_DEFAULT_TERMINAL_WIDTH = 80
# Budget for tailed log lines when no terminal width is known, e.g. when the
# dashboard is redirected to a file.
_DEFAULT_LOG_WIDTH = 140


def parse_upid(line: str) -> dict[str, str] | None:
    """Parse one active tasks line into a normalized task dict."""
    raw_line = line.rstrip("\n")
    if not raw_line:
        return None

    upid = raw_line.split(maxsplit=1)[0]
    trailing = raw_line[len(upid) :]
    if trailing.startswith("  ") or not trailing.strip():
        status = ""
    else:
        status = trailing.strip().split(maxsplit=1)[0]

    upid_parts = upid.split(":")
    action = upid_parts[5] if len(upid_parts) > 5 else ""

    return {"upid": upid, "action": action, "status": status, "raw": raw_line}


def read_active_tasks(active_path: str | None = None) -> list[dict[str, str]]:
    """Read active tasks file and keep only active statuses."""
    path = (
        Path(active_path) if active_path else Path(TASKS_LOG_DIR) / ACTIVE_TASKS_INDEX
    )
    if not path.exists():
        return []

    tasks: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parsed = parse_upid(line)
            if not parsed:
                continue
            if parsed["status"] in ACTIVE_STATUS_MARKERS:
                tasks.append(parsed)

    return tasks


def filter_restore_tasks(tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter tasks down to restore-like actions or UPID markers."""
    restore_tasks: list[dict[str, str]] = []
    for task in tasks:
        action = task.get("action", "").lower()
        task_text = f"{task.get('upid', '')} {task.get('raw', '')}".lower()
        if action in RESTORE_ACTION_MARKERS:
            restore_tasks.append(task)
            continue
        if any(keyword in task_text for keyword in RESTORE_KEYWORD_MARKERS):
            restore_tasks.append(task)

    return restore_tasks


def find_task_logfile(
    upid_str: str, tasks_root: str | Path | None = None
) -> Path | None:
    """Resolve task logfile path for a given UPID string."""
    upid_parts = upid_str.split(":")
    if len(upid_parts) < 8 or upid_parts[0] != "UPID":
        return None

    starttime = upid_parts[4]
    if not re.fullmatch(r"[0-9A-Fa-f]{8}", starttime):
        return None

    # Proxmox shards task logs into 16 folders keyed on the *last* hex digit of
    # the starttime field, matching substr($starttime, 7, 1) in
    # PVE::RESTEnvironment::fork_worker.
    expected_folder = starttime[-1].upper()
    if expected_folder not in HEX_ARCHIVE_FOLDERS:
        return None

    root = Path(tasks_root) if tasks_root is not None else Path(TASKS_LOG_DIR)

    preferred = root / expected_folder / upid_str
    if preferred.exists():
        return preferred

    for folder in HEX_ARCHIVE_FOLDERS:
        if folder == expected_folder:
            continue
        candidate = root / folder / upid_str
        if candidate.exists():
            return candidate

    return None


def parse_progress_line(line: str) -> tuple[int, float, float | None] | None:
    """Parse one restore progress line into normalized elapsed and transfer values."""
    for pattern_name, pattern in _PROGRESS_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue

        if pattern_name == "size_with_total":
            elapsed_seconds = _parse_elapsed_seconds(match.group("elapsed"))
            transferred_gib = _to_gib(
                float(match.group("transferred")), match.group("unit")
            )
            total_gib = _to_gib(float(match.group("total")), match.group("total_unit"))
            return (elapsed_seconds, transferred_gib, total_gib)

        if pattern_name == "qmrestore_bytes_progress":
            percent = float(match.group("percent"))
            read_bytes = int(match.group("read_bytes"))
            duration_seconds = int(match.group("duration_seconds"))
            transferred_gib = _bytes_to_gib(read_bytes)
            if percent <= 0:
                return (duration_seconds, transferred_gib, None)
            total_gib = transferred_gib * 100 / percent
            return (duration_seconds, transferred_gib, total_gib)

        if pattern_name == "percent_only":
            elapsed_seconds = _parse_elapsed_seconds(match.group("elapsed"))
            return (elapsed_seconds, float(match.group("percent")), None)

    return None


def calculate_eta_and_speed(points: Sequence[ProgressPoint]) -> tuple[float, float]:
    """Calculate point-to-point speed and ETA from parsed progress history."""
    return calculate_eta_and_speed_with_memory(points, previous_speed=0.0)


def calculate_eta_and_speed_with_memory(
    points: Sequence[ProgressPoint], previous_speed: float = 0.0
) -> tuple[float, float]:
    """Calculate smoothed speed and ETA with last-speed fallback."""
    if len(points) < 2:
        return (previous_speed, math.inf)

    window = points[-6:]
    total_delta_seconds = 0
    total_delta_value = 0.0
    for previous_point, current_point in itertools.pairwise(window):
        previous_elapsed, previous_value, _ = previous_point
        elapsed_seconds, current_value, _ = current_point
        delta_seconds = elapsed_seconds - previous_elapsed
        delta_value = current_value - previous_value
        if delta_seconds > 0 and delta_value > 0:
            total_delta_seconds += delta_seconds
            total_delta_value += delta_value

    speed = previous_speed
    if total_delta_seconds > 0 and total_delta_value > 0:
        speed = total_delta_value / total_delta_seconds

    current_total = points[-1][2]
    if current_total is None or speed <= 0:
        return (speed, math.inf)

    current_value = points[-1][1]
    remaining = max(current_total - current_value, 0.0)
    return (speed, remaining / speed)


def build_metrics_line(points: Sequence[ProgressPoint]) -> str:
    """Build one dashboard line with progress, speed, and ETA metrics."""
    if not points:
        return "Progress: n/a | Speed: 0.00 | ETA: n/a"

    _, current_value, total_value = points[-1]
    speed, eta_seconds = calculate_eta_and_speed(points)

    if total_value is None:
        progress_text = f"Progress: {current_value:.1f}%"
        speed_text = f"Speed: {speed:.2f} %/s"
    else:
        percent = (current_value / total_value * 100) if total_value > 0 else 0.0
        progress_text = (
            f"Progress: {percent:.1f}% ({current_value:.2f}/{total_value:.2f} GiB)"
        )
        speed_text = f"Speed: {speed:.2f} GiB/s"

    eta_text = (
        "ETA: n/a" if math.isinf(eta_seconds) else f"ETA: {_format_eta(eta_seconds)}"
    )
    return f"{progress_text} | {speed_text} | {eta_text}"


def visible_length(text: str) -> int:
    """Count the screen columns one string occupies.

    Parameters
    ----------
    text : str
        Text that may embed ANSI color escapes.

    Returns
    -------
    int
        Number of printable characters, escapes excluded.
    """
    return len(_ANSI_PATTERN.sub("", text))


def clip_to_width(text: str, width: int) -> str:
    """Clip one string to a column budget without cutting an ANSI escape.

    A closing reset is appended when the text carried any color, so that a cut
    never leaks an unterminated escape into the rest of the terminal.

    Parameters
    ----------
    text : str
        Text to clip, possibly containing ANSI color escapes.
    width : int
        Maximum number of screen columns.

    Returns
    -------
    str
        The text, shortened when it did not fit.
    """
    if width <= 0 or visible_length(text) <= width:
        return text

    kept: list[str] = []
    visible = 0
    index = 0
    had_escape = False
    while index < len(text) and visible < width:
        escape = _ANSI_PATTERN.match(text, index)
        if escape:
            kept.append(escape.group())
            had_escape = True
            index = escape.end()
            continue
        kept.append(text[index])
        visible += 1
        index += 1

    clipped = "".join(kept)
    return f"{clipped}{_COLOR_RESET}" if had_escape else clipped


def detect_terminal_width(stream: TextIO | None) -> int:
    """Detect the usable width of the terminal behind one stream.

    Parameters
    ----------
    stream : TextIO or None
        Output stream to inspect.

    Returns
    -------
    int
        Terminal width in columns, falling back to 80 when unknown.
    """
    if stream is not None:
        try:
            return os.get_terminal_size(stream.fileno()).columns
        except (AttributeError, OSError, ValueError):
            # Not a real terminal, or a stream without a file descriptor.
            pass
    return shutil.get_terminal_size((_DEFAULT_TERMINAL_WIDTH, 24)).columns


def build_tqdm_line(
    points: Sequence[ProgressPoint],
    speed_gib_s: float,
    average_speed_gib_s: float,
    eta_seconds: float,
    waiting: bool = False,
    color: bool = False,
    width: int | None = None,
) -> str:
    """Build one tqdm-like status line.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Parsed progress history.
    speed_gib_s : float
        Current instantaneous speed in GiB/s.
    average_speed_gib_s : float
        Average speed over the full monitoring window in GiB/s.
    eta_seconds : float
        Estimated time remaining in seconds.
    waiting : bool
        Whether the monitor is idle waiting for new log data.
    color : bool
        Whether to apply ANSI color codes to the output.
    width : int, optional
        Terminal width to fit into. The progress bar shrinks first and the least
        useful metrics drop out before the completion ratio and the ETA, so that
        the line never wraps.
    """
    percent = 0.0
    transferred = 0.0
    total = None
    if points:
        _, transferred, total = points[-1]
        if total and total > 0:
            percent = max(0.0, min(100.0, (transferred / total) * 100))
        else:
            percent = max(0.0, min(100.0, transferred))

    speed_mib_s = speed_gib_s * 1024
    average_speed_mib_s = average_speed_gib_s * 1024
    eta_text = "n/a" if math.isinf(eta_seconds) else _format_eta(eta_seconds)
    waiting_text = " waiting log" if waiting else ""
    elapsed_text = "00:00:00"
    if points:
        elapsed_text = _format_eta(float(max(0, points[-1][0])))

    if total and total > 0:
        size_text = f"{transferred:6.2f}/{total:6.2f} GiB"
    else:
        size_text = f"{transferred:6.2f} %"

    now_speed = f"Now {speed_mib_s:6.1f} MiB/s"
    avg_speed = f"Avg {average_speed_mib_s:6.1f} MiB/s"
    if color:
        now_speed = f"Now {speed_mib_s:6.1f} {_COLOR_CYAN}MiB/s{_COLOR_RESET}"
        avg_speed = f"Avg {average_speed_mib_s:6.1f} {_COLOR_CYAN}MiB/s{_COLOR_RESET}"
    eta_label = f"{_COLOR_YELLOW}ETA{_COLOR_RESET}" if color else "ETA"

    # Metric fields in display order, each tagged with how expendable it is. A
    # narrow terminal drops the highest tags first, so it loses context before
    # it loses the completion ratio and the ETA.
    ordered_segments: tuple[tuple[int, str], ...] = (
        (0, f"{percent:5.1f}%"),
        (3, size_text),
        (2, now_speed),
        (4, avg_speed),
        (5, f"Elapsed {elapsed_text}"),
        (1, f"{eta_label} {eta_text}{waiting_text}"),
    )

    def _suffix(max_tag: int) -> str:
        """Join the segments that fit within the given expendability budget."""
        kept = [text for tag, text in ordered_segments if tag <= max_tag]
        return " " + " | ".join(kept)

    suffix = _suffix(_MOST_EXPENDABLE_SEGMENT)
    bar_width = _MAX_BAR_WIDTH
    if width is not None:
        # Two columns go to the bar's brackets. A wrapped line would
        # desynchronize the in-place redraw, which counts screen rows rather
        # than logical lines.
        for max_tag in range(_MOST_EXPENDABLE_SEGMENT, 0, -1):
            candidate = _suffix(max_tag)
            available = width - visible_length(candidate) - 2
            if available >= _MIN_BAR_WIDTH or max_tag == 1:
                suffix = candidate
                bar_width = max(_MIN_BAR_WIDTH, min(_MAX_BAR_WIDTH, available))
                break

    filled = int((percent / 100) * bar_width)
    bar_inner = f"{'=' * filled}{'.' * (bar_width - filled)}"
    bar = f"{_COLOR_GREEN}[{bar_inner}]{_COLOR_RESET}" if color else f"[{bar_inner}]"

    line = f"{bar}{suffix}"
    return line if width is None else clip_to_width(line, width)


def build_dashboard_lines(
    points: Sequence[ProgressPoint],
    speed_gib_s: float,
    average_speed_gib_s: float,
    eta_seconds: float,
    recent_logs: list[str],
    waiting: bool = False,
    color: bool = False,
    width: int | None = None,
) -> list[str]:
    """Build one status line plus up to five recent log lines.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Parsed progress history.
    speed_gib_s : float
        Current instantaneous speed in GiB/s.
    average_speed_gib_s : float
        Average speed over the full monitoring window in GiB/s.
    eta_seconds : float
        Estimated time remaining in seconds.
    recent_logs : list[str]
        Recently seen log lines, oldest first.
    waiting : bool
        Whether the monitor is idle waiting for new log data.
    color : bool
        Whether to apply ANSI color codes to the output.
    width : int, optional
        Terminal width every line must fit into.

    Returns
    -------
    list[str]
        The dashboard block, status line first.
    """
    status_line = build_tqdm_line(
        points,
        speed_gib_s,
        average_speed_gib_s,
        eta_seconds,
        waiting=waiting,
        color=color,
        width=width,
    )

    # Log lines are indented by two columns, which eats into their budget.
    log_budget = _DEFAULT_LOG_WIDTH if width is None else max(width - 2, 1)

    lines = [status_line]
    for log_line in recent_logs[-5:]:
        rendered = _truncate(log_line, log_budget)
        if color:
            rendered = f"{_COLOR_DIM}{rendered}{_COLOR_RESET}"
        lines.append(f"  {rendered}")
    return lines


def render_dashboard(
    output_stream: TextIO,
    lines: list[str],
    previous_line_count: int,
    is_tty: bool,
) -> int:
    """Render dashboard lines, in place when output is a TTY."""
    if is_tty and previous_line_count > 0:
        output_stream.write(f"\033[{previous_line_count}A")

    # Cursor movement counts screen rows, not logical lines, so a single line
    # long enough to wrap would shift every following frame upward. Clipping
    # here guarantees one line equals one row.
    max_width = detect_terminal_width(output_stream) if is_tty else None

    for line in lines:
        if is_tty:
            output_stream.write("\033[2K")
        rendered = line if max_width is None else clip_to_width(line, max_width)
        output_stream.write(f"{rendered}\n")
    output_stream.flush()
    return len(lines)


def calculate_total_average_speed(points: Sequence[ProgressPoint]) -> float:
    """Calculate average speed from first to latest progress sample."""
    if len(points) < 2:
        return 0.0

    start_elapsed, start_value, _ = points[0]
    end_elapsed, end_value, _ = points[-1]
    elapsed_delta = end_elapsed - start_elapsed
    value_delta = end_value - start_value
    if elapsed_delta <= 0 or value_delta <= 0:
        return 0.0
    return value_delta / elapsed_delta


def _format_eta(eta_seconds: float) -> str:
    """Format ETA seconds into hh:mm:ss."""
    total_seconds = max(0, round(eta_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _parse_elapsed_seconds(elapsed: str) -> int:
    """Convert a Proxmox-rendered duration to total seconds.

    Accepts any subset of the units ``PVE::Format::render_duration`` may emit,
    so a restore running past the hour mark keeps a monotonic elapsed time.

    Parameters
    ----------
    elapsed : str
        Duration text such as ``45s``, ``1m 31s``, ``2h 5m 3s`` or ``1d 2h``.

    Returns
    -------
    int
        Total seconds, or 0 when no unit could be read.
    """
    total = 0
    for suffix, unit_seconds in _DURATION_UNIT_SECONDS.items():
        match = re.search(rf"(\d+){suffix}", elapsed)
        if match:
            total += int(match.group(1)) * unit_seconds
    return total


def _to_gib(value: float, unit: str) -> float:
    """Convert one IEC size value into GiB.

    Parameters
    ----------
    value : float
        Numeric size as printed in the log.
    unit : str
        IEC unit name, case-insensitive (``B`` through ``PiB``).

    Returns
    -------
    float
        Size expressed in GiB, or 0.0 for an unknown unit.
    """
    return value * _SIZE_UNIT_TO_GIB.get(unit.lower(), 0.0)


def _bytes_to_gib(value: int) -> float:
    """Convert bytes value to GiB."""
    return value / (1024**3)


def _truncate(value: str, length: int) -> str:
    """Truncate one string to target length with ellipsis."""
    if len(value) <= length:
        return value
    if length <= 3:
        return value[:length]
    return f"{value[: length - 3]}..."


def detect_terminal_status(line: str) -> TerminalStatus:
    """Detect whether one log line reports a terminal restore status.

    Parameters
    ----------
    line : str
        One line from the task log.

    Returns
    -------
    str or None
        ``"failure"``, ``"warnings"``, ``"success"``, or None while the restore
        is still running.
    """
    lowered = line.lower()
    if any(marker in lowered for marker in _FAILURE_STATUS_MARKERS):
        return "failure"
    if any(marker in lowered for marker in _WARNING_STATUS_MARKERS):
        return "warnings"
    if any(marker in lowered for marker in _SUCCESS_STATUS_MARKERS):
        return "success"
    return None


def debug_log(enabled: bool, message: str, stream: TextIO | None = None) -> None:
    """Print one debug line to stderr when debug mode is enabled."""
    if not enabled:
        return
    target = stream if stream is not None else sys.stderr
    print(f"[debug] {message}", file=target, flush=True)


def map_final_status_message(status: str | None) -> str:
    """Map one terminal status value to a final summary line."""
    summary_by_status = {
        "success": "Final status: success",
        "warnings": "Final status: success with warnings",
        "failure": "Final status: failure",
        "interrupted": "Final status: interrupted",
        "no-task": "Final status: no-task",
        "log-missing": "Final status: log-missing",
    }
    if status is None:
        return "Final status: unknown"
    return summary_by_status.get(status, "Final status: unknown")


def choose_restore_task(tasks: list[dict[str, str]]) -> dict[str, str] | None:
    """Choose one restore task to monitor."""
    if not tasks:
        return None
    if len(tasks) == 1:
        return tasks[0]
    return tasks[-1]


def resolve_restore_logfile(
    task: dict[str, str], tasks_root: str | Path | None = None
) -> Path | None:
    """Resolve a logfile path from a restore task dictionary."""
    upid = task.get("upid", "")
    if not upid:
        return None
    return find_task_logfile(upid, tasks_root=tasks_root)


def follow_log_lines(
    log_path: Path, idle_timeout_seconds: float = 600.0
) -> Iterator[str]:
    """Yield lines from a task logfile as they appear.

    Parameters
    ----------
    log_path : Path
        Path to the task log file to follow.
    idle_timeout_seconds : float
        Maximum seconds to wait without new data before stopping.
        Defaults to 600 (10 minutes).

    Yields
    ------
    str
        Each log line stripped of trailing newline, or empty string
        when no new data is available yet.
    """
    with log_path.open(encoding="utf-8") as handle:
        idle_elapsed = 0.0
        poll_interval = 0.2
        while True:
            line = handle.readline()
            if line:
                idle_elapsed = 0.0
                yield line.rstrip("\n")
                continue
            idle_elapsed += poll_interval
            if idle_elapsed >= idle_timeout_seconds:
                return
            time.sleep(poll_interval)
            yield ""


def collect_monitoring_data(
    log_lines: Iterable[str],
    *,
    output_stream: TextIO | None = None,
    update_interval_seconds: float = 1.0,
    now_fn: Callable[[], float] | None = None,
    debug: bool = False,
    debug_stream: TextIO | None = None,
) -> tuple[list[ProgressPoint], str | None]:
    """Collect progress points until terminal status or interruption."""
    points: list[ProgressPoint] = []
    recent_logs: collections.deque[str] = collections.deque(maxlen=5)
    now_getter = now_fn if now_fn is not None else time.monotonic
    last_output_time = now_getter()
    last_seen_line = ""
    last_speed = 0.0
    last_eta = math.inf
    previous_line_count = 0
    tty_mode = bool(
        output_stream and hasattr(output_stream, "isatty") and output_stream.isatty()
    )
    color_mode = tty_mode

    def render_width() -> int | None:
        """Return the column budget for one frame, re-read on every render.

        Re-reading keeps a resized window honored, and one column is kept spare
        to stay clear of deferred-wrap quirks.
        """
        return detect_terminal_width(output_stream) - 1 if tty_mode else None

    try:
        for line in log_lines:
            if line:
                last_seen_line = line
                recent_logs.append(line)
            progress = parse_progress_line(line)
            if progress is not None:
                points.append(progress)
                last_speed, last_eta = calculate_eta_and_speed_with_memory(
                    points, previous_speed=last_speed
                )
                if output_stream is not None:
                    lines = build_dashboard_lines(
                        points,
                        last_speed,
                        calculate_total_average_speed(points),
                        last_eta,
                        list(recent_logs),
                        waiting=False,
                        color=color_mode,
                        width=render_width(),
                    )
                    previous_line_count = render_dashboard(
                        output_stream, lines, previous_line_count, tty_mode
                    )
                last_output_time = now_getter()
            elif line:
                debug_log(debug, f"Ignored non-progress log line: {line}", debug_stream)

            current_time = now_getter()
            if (
                output_stream is not None
                and current_time - last_output_time >= update_interval_seconds
            ):
                if not recent_logs and last_seen_line:
                    recent_logs.append(last_seen_line)
                lines = build_dashboard_lines(
                    points,
                    last_speed,
                    calculate_total_average_speed(points),
                    last_eta,
                    list(recent_logs),
                    waiting=True,
                    color=color_mode,
                    width=render_width(),
                )
                previous_line_count = render_dashboard(
                    output_stream, lines, previous_line_count, tty_mode
                )
                last_output_time = current_time

            terminal_status = detect_terminal_status(line)
            if terminal_status is not None:
                debug_log(
                    debug, f"Detected terminal status: {terminal_status}", debug_stream
                )
                return points, terminal_status
    except KeyboardInterrupt:
        debug_log(debug, "Monitoring interrupted by user", debug_stream)
        return points, "interrupted"

    return points, None


def monitor_restore_task(
    task: dict[str, str],
    tasks_root: str | Path | None = None,
    log_lines: Iterable[str] | None = None,
    output_stream: TextIO | None = None,
    update_interval_seconds: float = 1.0,
    now_fn: Callable[[], float] | None = None,
    debug: bool = False,
    debug_stream: TextIO | None = None,
) -> tuple[list[ProgressPoint], str | None]:
    """Run the minimal monitoring flow for one restore task."""
    logfile = resolve_restore_logfile(task, tasks_root=tasks_root)
    if logfile is None:
        debug_log(debug, "Could not resolve task logfile", debug_stream)
        return [], "log-missing"

    stream = log_lines if log_lines is not None else follow_log_lines(logfile)
    return collect_monitoring_data(
        stream,
        output_stream=output_stream,
        update_interval_seconds=update_interval_seconds,
        now_fn=now_fn,
        debug=debug,
        debug_stream=debug_stream,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the restore watcher."""
    parser = argparse.ArgumentParser(description="Monitor Proxmox restore tasks")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logs on stderr",
    )
    return parser.parse_args(argv if argv is not None else [])


def main(argv: list[str] | None = None) -> None:
    """Run the restore watcher CLI."""
    args = parse_args(argv)
    final_status: str | None = None

    try:
        active_tasks = read_active_tasks()
        debug_log(args.debug, f"Loaded {len(active_tasks)} active tasks")
        restore_tasks = filter_restore_tasks(active_tasks)
        debug_log(args.debug, f"Filtered {len(restore_tasks)} restore-like tasks")
        selected_task = choose_restore_task(restore_tasks)
        if selected_task is None:
            final_status = "no-task"
            return

        upid = selected_task.get("upid", "unknown")
        action = selected_task.get("action", "unknown")
        print(f"Monitoring restore task: action={action} upid={upid}", flush=True)

        logfile = resolve_restore_logfile(selected_task)
        if logfile is None:
            final_status = "log-missing"
            return

        print(f"Log file: {logfile}", flush=True)
        debug_log(args.debug, f"Resolved logfile path: {logfile}")

        _, final_status = monitor_restore_task(
            selected_task,
            output_stream=sys.stdout,
            debug=args.debug,
            debug_stream=sys.stderr,
        )
    finally:
        print(map_final_status_message(final_status), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
