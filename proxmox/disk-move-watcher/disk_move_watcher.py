"""CLI tool to monitor active Proxmox disk move tasks from task logs.

Proxmox exposes two worker types for moving a volume between storages:
``qmmove`` for QEMU virtual machines (``qm move-disk``) and ``move_volume``
for LXC containers (``pct move-volume``). Both write their progress into
``/var/log/pve/tasks/<hex>/<upid>``, which this module follows and renders
as a tqdm-style dashboard.

Unlike restore tasks, a disk move has two very different progress shapes:

* offline moves run ``qemu-img convert`` and print a transferred/total pair
  **without** any elapsed time, so samples must be stamped from the wall clock;
* online moves drive a QEMU block job and prefix every line with the drive
  name, including an ``in <duration>`` field.

A single task may also move several drives one after the other. Progress
history is therefore reset whenever the reported drive changes, so speed and
ETA never mix two unrelated transfers.
"""

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

MOVE_ACTION_MARKERS = ["qmmove", "move_volume"]
MOVE_KEYWORD_MARKERS = ["move-disk", "move_disk", "move-volume"]
ACTIVE_STATUS_MARKERS = {"", "0"}

TASKS_LOG_DIR = "/var/log/pve/tasks"
ACTIVE_TASKS_INDEX = "active"
HEX_ARCHIVE_FOLDERS = "0123456789ABCDEF"

IDLE_TIMEOUT_SECONDS = 600.0

# Proxmox renders sizes through PVE::Tools::render_bytes, which emits IEC
# units. Longer unit names must come first in the alternation so that "MiB"
# is never truncated to a bare "B" match.
_SIZE_UNIT_ALTERNATION = "KiB|MiB|GiB|TiB|PiB|B"
_SIZE_UNIT_TO_GIB: dict[str, float] = {
    "b": 1 / (1024**3),
    "kib": 1 / (1024**2),
    "mib": 1 / 1024,
    "gib": 1.0,
    "tib": 1024.0,
    "pib": 1024.0**2,
}

# PVE::Format::render_duration joins the largest non-zero units among
# weeks, days, hours, minutes and seconds, e.g. "0s", "3s", "1m 31s", "1d 2h".
_DURATION_PATTERN = r"(?:\d+[wdhms]\s*)+"
_DURATION_UNIT_SECONDS: dict[str, int] = {
    "w": 7 * 24 * 3600,
    "d": 24 * 3600,
    "h": 3600,
    "m": 60,
    "s": 1,
}

# Both the offline qemu-img convert path and the online block-job path print
# a transferred/total pair. The drive prefix and the trailing duration are
# optional because only the online path emits them, and that path may append
# ", ready" or ", still busy" after the duration.
_PROGRESS_PATTERN = re.compile(
    r"(?:(?P<drive>[\w\-.]+):\s+)?"
    r"transferred\s+(?P<transferred>\d+(?:\.\d+)?)\s*"
    rf"(?P<unit>{_SIZE_UNIT_ALTERNATION})\b\s+of\s+"
    r"(?P<total>\d+(?:\.\d+)?)\s*"
    rf"(?P<total_unit>{_SIZE_UNIT_ALTERNATION})\b"
    r"(?:\s*\((?P<percent>\d+(?:\.\d+)?)\s*%\))?"
    rf"(?:\s+in\s+(?P<elapsed>{_DURATION_PATTERN}))?",
    flags=re.IGNORECASE,
)

# (elapsed_seconds, transferred_gib, total_gib, drive_name); elapsed is None on
# the offline path, and total is None only when the log reports a zero size.
ProgressSample = tuple[int | None, float, float | None, str | None]
# (elapsed_seconds, transferred_gib, total_gib) once stamped and normalized.
ProgressPoint = tuple[int, float, float | None]
TerminalStatus = str | None

# Only the worker epilogue is terminal for the whole task. "Completed
# successfully" is deliberately absent: it marks the end of one block job, and
# a single task may move several drives in a row.
_SUCCESS_STATUS_MARKERS = ("task ok",)
_FAILURE_STATUS_MARKERS = ("task error",)
# A task that finishes with warnings ends on TASK WARNINGS instead of TASK OK,
# so it has to be treated as terminal too or the watcher would wait for the
# idle timeout on an already finished move.
_WARNING_STATUS_MARKERS = ("task warnings",)

# Milestones worth surfacing even though they carry no numeric progress.
_MILESTONE_MARKERS = (
    "copying volume",
    "create full clone of drive",
    "create linked clone of drive",
    # Emitted by qemu-img itself when it preallocates the target image.
    "formatting '",
    "allocated target volume",
    "moving disk with snapshots",
    "drive mirror is starting",
    "drive mirror re-using dirty bitmap",
    "all 'mirror' jobs are ready",
    "completing block job",
    "completed successfully",
    "adding source volume",
    "removing source volume",
    "reassign disk",
    "removing disk",
    "moving volume",
    "removing volume",
)

_COLOR_RESET = "\033[0m"
_COLOR_GREEN = "\033[32m"
_COLOR_CYAN = "\033[36m"
_COLOR_YELLOW = "\033[33m"
_COLOR_MAGENTA = "\033[35m"
_COLOR_DIM = "\033[2m"

# Color escapes take no screen columns, so they must be discounted before any
# width computation.
_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

_MIN_BAR_WIDTH = 8
_MAX_BAR_WIDTH = 24
# Highest expendability tag used by the status line segments; see
# build_tqdm_line for the ordering.
_MOST_EXPENDABLE_SEGMENT = 5
_DEFAULT_TERMINAL_WIDTH = 80
# Budget for tailed log lines when no terminal width is known, e.g. when the
# dashboard is redirected to a file.
_DEFAULT_LOG_WIDTH = 140


def parse_upid(line: str) -> dict[str, str] | None:
    """Parse one active tasks line into a normalized task dict.

    Parameters
    ----------
    line : str
        One raw line from ``/var/log/pve/tasks/active``, shaped as
        ``UPID:node:pid:pstart:starttime:type:id:user: [status]``.

    Returns
    -------
    dict[str, str] or None
        Mapping with ``upid``, ``node``, ``action``, ``vmid``, ``status`` and
        ``raw`` keys, or None when the line is empty.
    """
    raw_line = line.rstrip("\n")
    if not raw_line:
        return None

    upid = raw_line.split(maxsplit=1)[0]
    trailing = raw_line[len(upid) :]
    # An active task has no status column; a finished one appends its exit
    # status after the UPID, separated by a single space.
    if trailing.startswith("  ") or not trailing.strip():
        status = ""
    else:
        status = trailing.strip().split(maxsplit=1)[0]

    upid_parts = upid.split(":")
    node = upid_parts[1] if len(upid_parts) > 1 else ""
    action = upid_parts[5] if len(upid_parts) > 5 else ""
    vmid = upid_parts[6] if len(upid_parts) > 6 else ""

    return {
        "upid": upid,
        "node": node,
        "action": action,
        "vmid": vmid,
        "status": status,
        "raw": raw_line,
    }


def read_active_tasks(active_path: str | None = None) -> list[dict[str, str]]:
    """Read the active tasks index and keep only still-running entries.

    Parameters
    ----------
    active_path : str, optional
        Override for the active tasks index path, used by tests.

    Returns
    -------
    list[dict[str, str]]
        Parsed tasks whose status marks them as still running.
    """
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


def filter_disk_move_tasks(tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter tasks down to disk move worker types.

    Parameters
    ----------
    tasks : list[dict[str, str]]
        Parsed active tasks.

    Returns
    -------
    list[dict[str, str]]
        Tasks whose worker type is a VM disk move or an LXC volume move.
    """
    move_tasks: list[dict[str, str]] = []
    for task in tasks:
        action = task.get("action", "").lower()
        if action in MOVE_ACTION_MARKERS:
            move_tasks.append(task)
            continue
        task_text = f"{task.get('upid', '')} {task.get('raw', '')}".lower()
        if any(keyword in task_text for keyword in MOVE_KEYWORD_MARKERS):
            move_tasks.append(task)

    return move_tasks


def find_task_logfile(
    upid_str: str, tasks_root: str | Path | None = None
) -> Path | None:
    """Resolve the task logfile path for a given UPID string.

    Parameters
    ----------
    upid_str : str
        Full UPID of the task.
    tasks_root : str or Path, optional
        Override for the task log root, used by tests.

    Returns
    -------
    Path or None
        Path to the log file, or None when it cannot be located.
    """
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


def parse_size_to_gib(value: float, unit: str) -> float:
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


def parse_duration_seconds(elapsed: str | None) -> int | None:
    """Convert a Proxmox-rendered duration into whole seconds.

    Accepts any subset of the ``w``, ``d``, ``h``, ``m`` and ``s`` units that
    ``PVE::Format::render_duration`` may emit, such as ``0s``, ``1m 31s`` or
    ``1d 2h``.

    Parameters
    ----------
    elapsed : str or None
        Duration text, or None when the log line omits it.

    Returns
    -------
    int or None
        Total seconds, or None when nothing could be parsed.
    """
    if not elapsed:
        return None

    total = 0
    matched = False
    for suffix, unit_seconds in _DURATION_UNIT_SECONDS.items():
        match = re.search(rf"(\d+){suffix}", elapsed)
        if match:
            matched = True
            total += int(match.group(1)) * unit_seconds
    return total if matched else None


def parse_progress_line(line: str) -> ProgressSample | None:
    """Parse one log line into a normalized progress sample.

    Parameters
    ----------
    line : str
        One line from the task log.

    Returns
    -------
    ProgressSample or None
        ``(elapsed_seconds, transferred_gib, total_gib, drive)`` where elapsed
        is None on the offline path, or None when the line carries no progress.
    """
    match = _PROGRESS_PATTERN.search(line)
    if not match:
        return None

    transferred_gib = parse_size_to_gib(
        float(match.group("transferred")), match.group("unit")
    )
    total_gib = parse_size_to_gib(
        float(match.group("total")), match.group("total_unit")
    )
    return (
        parse_duration_seconds(match.group("elapsed")),
        transferred_gib,
        # A zero total would only lead to a division by zero downstream.
        total_gib or None,
        match.group("drive"),
    )


def detect_milestone(line: str) -> str | None:
    """Detect a non-numeric disk move milestone in one log line.

    Parameters
    ----------
    line : str
        One line from the task log.

    Returns
    -------
    str or None
        The matched milestone marker, or None when the line is not a milestone.
    """
    lowered = line.lower()
    for marker in _MILESTONE_MARKERS:
        if marker in lowered:
            return marker
    return None


def detect_terminal_status(line: str) -> TerminalStatus:
    """Detect whether one log line reports a terminal task status.

    Parameters
    ----------
    line : str
        One line from the task log.

    Returns
    -------
    str or None
        ``"failure"``, ``"warnings"``, ``"success"``, or None when the task is
        still running.
    """
    lowered = line.lower()
    if any(marker in lowered for marker in _FAILURE_STATUS_MARKERS):
        return "failure"
    if any(marker in lowered for marker in _WARNING_STATUS_MARKERS):
        return "warnings"
    if any(marker in lowered for marker in _SUCCESS_STATUS_MARKERS):
        return "success"
    return None


def calculate_eta_and_speed(points: Sequence[ProgressPoint]) -> tuple[float, float]:
    """Calculate point-to-point speed and ETA from parsed progress history.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Stamped progress history.

    Returns
    -------
    tuple[float, float]
        Speed in GiB/s and ETA in seconds (``math.inf`` when unknown).
    """
    return calculate_eta_and_speed_with_memory(points, previous_speed=0.0)


def calculate_eta_and_speed_with_memory(
    points: Sequence[ProgressPoint], previous_speed: float = 0.0
) -> tuple[float, float]:
    """Calculate smoothed speed and ETA, falling back to the last known speed.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Stamped progress history.
    previous_speed : float
        Speed to keep when the current window yields no usable delta.

    Returns
    -------
    tuple[float, float]
        Speed in GiB/s and ETA in seconds (``math.inf`` when unknown).
    """
    if len(points) < 2:
        return (previous_speed, math.inf)

    # A short trailing window keeps the readout responsive without letting a
    # single stalled sample zero out the speed.
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


def calculate_total_average_speed(points: Sequence[ProgressPoint]) -> float:
    """Calculate average speed from the first to the latest progress sample.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Stamped progress history.

    Returns
    -------
    float
        Average speed in GiB/s, or 0.0 when it cannot be derived.
    """
    if len(points) < 2:
        return 0.0

    start_elapsed, start_value, _ = points[0]
    end_elapsed, end_value, _ = points[-1]
    elapsed_delta = end_elapsed - start_elapsed
    value_delta = end_value - start_value
    if elapsed_delta <= 0 or value_delta <= 0:
        return 0.0
    return value_delta / elapsed_delta


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
    drive: str | None = None,
    waiting: bool = False,
    color: bool = False,
    width: int | None = None,
) -> str:
    """Build one tqdm-like status line.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Stamped progress history.
    speed_gib_s : float
        Current instantaneous speed in GiB/s.
    average_speed_gib_s : float
        Average speed over the full monitoring window in GiB/s.
    eta_seconds : float
        Estimated time remaining in seconds.
    drive : str, optional
        Name of the drive currently being moved.
    waiting : bool
        Whether the monitor is idle waiting for new log data.
    color : bool
        Whether to apply ANSI color codes to the output.
    width : int, optional
        Terminal width to fit into. The progress bar shrinks before anything
        else, and the line is clipped as a last resort so that it never wraps.

    Returns
    -------
    str
        The rendered status line.
    """
    percent = 0.0
    transferred = 0.0
    total = None
    if points:
        _, transferred, total = points[-1]
        if total and total > 0:
            percent = max(0.0, min(100.0, (transferred / total) * 100))

    speed_mib_s = speed_gib_s * 1024
    average_speed_mib_s = average_speed_gib_s * 1024
    eta_text = "n/a" if math.isinf(eta_seconds) else format_duration(eta_seconds)
    waiting_text = " waiting log" if waiting else ""
    elapsed_text = "00:00:00"
    if points:
        elapsed_text = format_duration(float(max(0, points[-1][0])))

    if total and total > 0:
        size_text = f"{transferred:6.2f}/{total:6.2f} GiB"
    else:
        size_text = f"{transferred:6.2f}/     ? GiB"

    drive_text = ""
    if drive:
        label = f"{_COLOR_MAGENTA}{drive}{_COLOR_RESET}" if color else drive
        drive_text = f"{label} "

    now_speed = f"Now {speed_mib_s:6.1f} MiB/s"
    avg_speed = f"Avg {average_speed_mib_s:6.1f} MiB/s"
    if color:
        now_speed = f"Now {speed_mib_s:6.1f} {_COLOR_CYAN}MiB/s{_COLOR_RESET}"
        avg_speed = f"Avg {average_speed_mib_s:6.1f} {_COLOR_CYAN}MiB/s{_COLOR_RESET}"
    eta_label = f"{_COLOR_YELLOW}ETA{_COLOR_RESET}" if color else "ETA"

    # Metric fields in display order, each tagged with how expendable it is.
    # A narrow terminal drops the highest tags first, so it loses context
    # before it loses the completion ratio and the ETA.
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
        # Two columns go to the bar's brackets. Shrink the bar first, then start
        # dropping metrics; a wrapped line would desynchronize the in-place
        # redraw, which counts screen rows rather than logical lines.
        fixed_width = visible_length(drive_text) + 2
        for max_tag in range(_MOST_EXPENDABLE_SEGMENT, 0, -1):
            candidate = _suffix(max_tag)
            available = width - fixed_width - visible_length(candidate)
            if available >= _MIN_BAR_WIDTH or max_tag == 1:
                suffix = candidate
                bar_width = max(_MIN_BAR_WIDTH, min(_MAX_BAR_WIDTH, available))
                break

    filled = int((percent / 100) * bar_width)
    bar_inner = f"{'=' * filled}{'.' * (bar_width - filled)}"
    bar = f"{_COLOR_GREEN}[{bar_inner}]{_COLOR_RESET}" if color else f"[{bar_inner}]"

    line = f"{drive_text}{bar}{suffix}"
    return line if width is None else clip_to_width(line, width)


def build_dashboard_lines(
    points: Sequence[ProgressPoint],
    speed_gib_s: float,
    average_speed_gib_s: float,
    eta_seconds: float,
    recent_logs: list[str],
    drive: str | None = None,
    waiting: bool = False,
    color: bool = False,
    width: int | None = None,
) -> list[str]:
    """Build one status line plus up to five recent log lines.

    Parameters
    ----------
    points : Sequence[ProgressPoint]
        Stamped progress history.
    speed_gib_s : float
        Current instantaneous speed in GiB/s.
    average_speed_gib_s : float
        Average speed over the full monitoring window in GiB/s.
    eta_seconds : float
        Estimated time remaining in seconds.
    recent_logs : list[str]
        Recently seen log lines, oldest first.
    drive : str, optional
        Name of the drive currently being moved.
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
        drive=drive,
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
    """Render dashboard lines, in place when the output is a TTY.

    Parameters
    ----------
    output_stream : TextIO
        Stream to write to.
    lines : list[str]
        Dashboard block to render.
    previous_line_count : int
        Number of lines written by the previous render.
    is_tty : bool
        Whether cursor movement is allowed.

    Returns
    -------
    int
        Number of lines written, to feed the next call.
    """
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


def format_duration(total_seconds: float) -> str:
    """Format a number of seconds into ``hh:mm:ss``.

    Parameters
    ----------
    total_seconds : float
        Duration in seconds; negative values are clamped to zero.

    Returns
    -------
    str
        Zero-padded ``hh:mm:ss`` text.
    """
    seconds_total = max(0, round(total_seconds))
    hours, remainder = divmod(seconds_total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _truncate(value: str, length: int) -> str:
    """Truncate one string to a target length with an ellipsis.

    Parameters
    ----------
    value : str
        Text to shorten.
    length : int
        Maximum output length.

    Returns
    -------
    str
        The possibly shortened text.
    """
    if len(value) <= length:
        return value
    if length <= 3:
        return value[:length]
    return f"{value[: length - 3]}..."


def debug_log(enabled: bool, message: str, stream: TextIO | None = None) -> None:
    """Print one debug line to stderr when debug mode is enabled.

    Parameters
    ----------
    enabled : bool
        Whether debug output is requested.
    message : str
        Message to emit.
    stream : TextIO, optional
        Target stream; defaults to stderr.
    """
    if not enabled:
        return
    target = stream if stream is not None else sys.stderr
    print(f"[debug] {message}", file=target, flush=True)


def map_final_status_message(status: str | None) -> str:
    """Map one terminal status value to a final summary line.

    Parameters
    ----------
    status : str or None
        Terminal status recorded by the monitoring loop.

    Returns
    -------
    str
        Human-readable summary line.
    """
    summary_by_status = {
        "success": "Final status: success",
        "warnings": "Final status: success with warnings",
        "failure": "Final status: failure",
        "interrupted": "Final status: interrupted",
        "no-task": "Final status: no-task",
        "log-missing": "Final status: log-missing",
        "idle-timeout": "Final status: idle-timeout",
    }
    if status is None:
        return "Final status: unknown"
    return summary_by_status.get(status, "Final status: unknown")


def choose_disk_move_task(
    tasks: list[dict[str, str]], upid: str | None = None
) -> dict[str, str] | None:
    """Choose one disk move task to monitor.

    Parameters
    ----------
    tasks : list[dict[str, str]]
        Candidate disk move tasks.
    upid : str, optional
        Exact UPID to select; when set, no other task is considered.

    Returns
    -------
    dict[str, str] or None
        The selected task, or None when nothing matches.
    """
    if upid:
        for task in tasks:
            if task.get("upid") == upid:
                return task
        return None
    if not tasks:
        return None
    if len(tasks) == 1:
        return tasks[0]
    # The most recently started task is the one the operator just triggered.
    return tasks[-1]


def resolve_disk_move_logfile(
    task: dict[str, str], tasks_root: str | Path | None = None
) -> Path | None:
    """Resolve a logfile path from a disk move task dictionary.

    Parameters
    ----------
    task : dict[str, str]
        Parsed task entry.
    tasks_root : str or Path, optional
        Override for the task log root, used by tests.

    Returns
    -------
    Path or None
        Path to the log file, or None when it cannot be located.
    """
    upid = task.get("upid", "")
    if not upid:
        return None
    return find_task_logfile(upid, tasks_root=tasks_root)


def follow_log_lines(
    log_path: Path, idle_timeout_seconds: float = IDLE_TIMEOUT_SECONDS
) -> Iterator[str]:
    """Yield lines from a task logfile as they appear.

    Parameters
    ----------
    log_path : Path
        Path to the task log file to follow.
    idle_timeout_seconds : float
        Maximum seconds to wait without new data before stopping.

    Yields
    ------
    str
        Each log line stripped of its trailing newline, or an empty string
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
    """Collect progress points until a terminal status or an interruption.

    Samples that carry no elapsed time (the offline ``qemu-img convert`` path)
    are stamped from ``now_fn``. When the reported drive changes, history is
    reset so that the speed and ETA of the new drive are not polluted by the
    previous one.

    Parameters
    ----------
    log_lines : Iterable[str]
        Source of log lines, typically :func:`follow_log_lines`.
    output_stream : TextIO, optional
        Stream for the live dashboard; None disables rendering.
    update_interval_seconds : float
        Minimum delay between two idle heartbeat renders.
    now_fn : Callable[[], float], optional
        Monotonic clock source, injectable for tests.
    debug : bool
        Whether to emit debug lines.
    debug_stream : TextIO, optional
        Target stream for debug lines.

    Returns
    -------
    tuple[list[ProgressPoint], str or None]
        Progress history of the last tracked drive and the terminal status.
    """
    points: list[ProgressPoint] = []
    recent_logs: collections.deque[str] = collections.deque(maxlen=5)
    now_getter = now_fn if now_fn is not None else time.monotonic
    start_time = now_getter()
    last_output_time = start_time
    last_seen_line = ""
    last_speed = 0.0
    last_eta = math.inf
    previous_line_count = 0
    current_drive: str | None = None
    tty_mode = bool(
        output_stream and hasattr(output_stream, "isatty") and output_stream.isatty()
    )
    color_mode = tty_mode

    def _render(waiting: bool) -> int:
        """Render the dashboard once and return the line count written."""
        if output_stream is None:
            return previous_line_count
        # Re-read the width on every frame so a resized window is honored, and
        # keep one column spare to stay clear of deferred-wrap quirks.
        render_width = detect_terminal_width(output_stream) - 1 if tty_mode else None
        lines = build_dashboard_lines(
            points,
            last_speed,
            calculate_total_average_speed(points),
            last_eta,
            list(recent_logs),
            drive=current_drive,
            waiting=waiting,
            color=color_mode,
            width=render_width,
        )
        return render_dashboard(output_stream, lines, previous_line_count, tty_mode)

    try:
        for line in log_lines:
            if line:
                last_seen_line = line
                recent_logs.append(line)

            sample = parse_progress_line(line)
            if sample is not None:
                elapsed_seconds, transferred_gib, total_gib, drive = sample
                if drive is not None and drive != current_drive:
                    if current_drive is not None:
                        debug_log(
                            debug,
                            f"Drive changed from {current_drive} to {drive}, "
                            "resetting progress history",
                            debug_stream,
                        )
                        points = []
                        last_speed = 0.0
                        last_eta = math.inf
                    current_drive = drive
                if elapsed_seconds is None:
                    # Offline moves print no duration; stamp from the clock.
                    elapsed_seconds = round(now_getter() - start_time)

                points.append((elapsed_seconds, transferred_gib, total_gib))
                last_speed, last_eta = calculate_eta_and_speed_with_memory(
                    points, previous_speed=last_speed
                )
                previous_line_count = _render(waiting=False)
                last_output_time = now_getter()
            elif line:
                milestone = detect_milestone(line)
                if milestone is not None:
                    debug_log(debug, f"Milestone: {line}", debug_stream)
                else:
                    debug_log(
                        debug, f"Ignored non-progress log line: {line}", debug_stream
                    )

            current_time = now_getter()
            if (
                output_stream is not None
                and current_time - last_output_time >= update_interval_seconds
            ):
                if not recent_logs and last_seen_line:
                    recent_logs.append(last_seen_line)
                previous_line_count = _render(waiting=True)
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

    # The line source ended without a terminal marker, which means the log
    # went quiet for longer than the idle timeout.
    return points, "idle-timeout"


def monitor_disk_move_task(
    task: dict[str, str],
    tasks_root: str | Path | None = None,
    log_lines: Iterable[str] | None = None,
    output_stream: TextIO | None = None,
    update_interval_seconds: float = 1.0,
    now_fn: Callable[[], float] | None = None,
    debug: bool = False,
    debug_stream: TextIO | None = None,
) -> tuple[list[ProgressPoint], str | None]:
    """Run the monitoring flow for one disk move task.

    Parameters
    ----------
    task : dict[str, str]
        Task to monitor.
    tasks_root : str or Path, optional
        Override for the task log root, used by tests.
    log_lines : Iterable[str], optional
        Pre-built line source, bypassing the log follower.
    output_stream : TextIO, optional
        Stream for the live dashboard.
    update_interval_seconds : float
        Minimum delay between two idle heartbeat renders.
    now_fn : Callable[[], float], optional
        Monotonic clock source, injectable for tests.
    debug : bool
        Whether to emit debug lines.
    debug_stream : TextIO, optional
        Target stream for debug lines.

    Returns
    -------
    tuple[list[ProgressPoint], str or None]
        Progress history and the terminal status.
    """
    logfile = resolve_disk_move_logfile(task, tasks_root=tasks_root)
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


def format_task_label(task: dict[str, str]) -> str:
    """Build a short human-readable label for one task.

    Parameters
    ----------
    task : dict[str, str]
        Parsed task entry.

    Returns
    -------
    str
        Label of the form ``<action> vmid=<id> node=<node>``.
    """
    action = task.get("action") or "unknown"
    vmid = task.get("vmid") or "n/a"
    node = task.get("node") or "n/a"
    return f"{action} vmid={vmid} node={node}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the disk move watcher.

    Parameters
    ----------
    argv : list[str], optional
        Argument vector; defaults to an empty list.

    Returns
    -------
    argparse.Namespace
        Parsed options.
    """
    parser = argparse.ArgumentParser(
        description="Monitor Proxmox disk move tasks (qmmove, move_volume)"
    )
    parser.add_argument(
        "--upid",
        default=None,
        help="Monitor this exact UPID instead of auto-selecting a task",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List active disk move tasks and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logs on stderr",
    )
    return parser.parse_args(argv if argv is not None else [])


def main(argv: list[str] | None = None) -> None:
    """Run the disk move watcher CLI.

    Parameters
    ----------
    argv : list[str], optional
        Argument vector; defaults to an empty list.
    """
    args = parse_args(argv)
    final_status: str | None = None
    print_summary = True

    try:
        active_tasks = read_active_tasks()
        debug_log(args.debug, f"Loaded {len(active_tasks)} active tasks")
        move_tasks = filter_disk_move_tasks(active_tasks)
        debug_log(args.debug, f"Filtered {len(move_tasks)} disk move tasks")

        if args.list:
            print_summary = False
            if not move_tasks:
                print("No active disk move task found.", flush=True)
                return
            for task in move_tasks:
                print(f"{task['upid']}  {format_task_label(task)}", flush=True)
            return

        selected_task = choose_disk_move_task(move_tasks, upid=args.upid)
        if selected_task is None:
            final_status = "no-task"
            return

        print(
            f"Monitoring disk move task: {format_task_label(selected_task)} "
            f"upid={selected_task.get('upid', 'unknown')}",
            flush=True,
        )

        logfile = resolve_disk_move_logfile(selected_task)
        if logfile is None:
            final_status = "log-missing"
            return

        print(f"Log file: {logfile}", flush=True)
        debug_log(args.debug, f"Resolved logfile path: {logfile}")

        _, final_status = monitor_disk_move_task(
            selected_task,
            output_stream=sys.stdout,
            debug=args.debug,
            debug_stream=sys.stderr,
        )
    finally:
        if print_summary:
            print(map_final_status_message(final_status), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
