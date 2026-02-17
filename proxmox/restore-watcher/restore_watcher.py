"""Placeholder CLI for Proxmox restore watcher."""

from __future__ import annotations

import argparse
import collections
import math
from pathlib import Path
import re
import sys
import time
from typing import Callable, Iterable, Iterator, Sequence, TextIO

RESTORE_ACTION_MARKERS = ["qmrestore", "pctrestore"]
RESTORE_KEYWORD_MARKERS = ["restore", "restoring", "backup"]
ACTIVE_STATUS_MARKERS = {"", "0"}

TASKS_LOG_DIR = "/var/log/pve/tasks"
ACTIVE_TASKS_INDEX = "active"
HEX_ARCHIVE_FOLDERS = "0123456789ABCDEF"
_PROGRESS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "size_with_total",
        re.compile(
            r"transferred\s+(?P<transferred>\d+(?:\.\d+)?)\s+"
            r"(?P<unit>GiB|MiB)\s+of\s+(?P<total>\d+(?:\.\d+)?)\s+"
            r"(?P<total_unit>GiB|MiB).*?\sin\s+(?P<elapsed>(?:\d+m\s+)?\d+s)",
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
            r"(?P<elapsed>(?:\d+m\s+)?\d+s)",
            flags=re.IGNORECASE,
        ),
    ),
)
ProgressPoint = tuple[int, float, float | None]
TerminalStatus = str | None

_SUCCESS_STATUS_MARKERS = ("task ok", "completed", "success")
_FAILURE_STATUS_MARKERS = ("task error", "failed", "aborted")
_COLOR_RESET = "\033[0m"
_COLOR_GREEN = "\033[32m"
_COLOR_CYAN = "\033[36m"
_COLOR_YELLOW = "\033[33m"
_COLOR_DIM = "\033[2m"


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

    pstart = upid_parts[4]
    if not re.fullmatch(r"[0-9A-Fa-f]{8}", pstart):
        return None

    expected_folder = pstart[0].upper()
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
    for previous_point, current_point in zip(window, window[1:]):
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


def build_tqdm_line(
    points: Sequence[ProgressPoint],
    speed_gib_s: float,
    average_speed_gib_s: float,
    eta_seconds: float,
    waiting: bool = False,
) -> str:
    """Build one tqdm-like status line."""
    percent = 0.0
    transferred = 0.0
    total = None
    if points:
        _, transferred, total = points[-1]
        if total and total > 0:
            percent = max(0.0, min(100.0, (transferred / total) * 100))
        else:
            percent = max(0.0, min(100.0, transferred))

    bar_width = 28
    filled = int((percent / 100) * bar_width)
    bar = f"[{'=' * filled}{'.' * (bar_width - filled)}]"
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

    return (
        f"{bar} {percent:5.1f}% | {size_text} | "
        f"Now {speed_mib_s:6.1f} MiB/s | Avg {average_speed_mib_s:6.1f} MiB/s | "
        f"Elapsed {elapsed_text} | ETA {eta_text}{waiting_text}"
    )


def build_dashboard_lines(
    points: Sequence[ProgressPoint],
    speed_gib_s: float,
    average_speed_gib_s: float,
    eta_seconds: float,
    recent_logs: list[str],
    waiting: bool = False,
    color: bool = False,
) -> list[str]:
    """Build one status line plus up to five recent log lines."""
    status_line = build_tqdm_line(
        points,
        speed_gib_s,
        average_speed_gib_s,
        eta_seconds,
        waiting=waiting,
    )
    if color:
        status_line = (
            status_line.replace("[", f"{_COLOR_GREEN}[")
            .replace("]", f"]{_COLOR_RESET}")
            .replace("MiB/s", f"{_COLOR_CYAN}MiB/s{_COLOR_RESET}")
            .replace("ETA", f"{_COLOR_YELLOW}ETA{_COLOR_RESET}")
        )

    lines = [status_line]
    for log_line in recent_logs[-5:]:
        rendered = _truncate(log_line, 140)
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

    for line in lines:
        if is_tty:
            output_stream.write("\033[2K")
        output_stream.write(f"{line}\n")
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
    total_seconds = max(0, int(round(eta_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _parse_elapsed_seconds(elapsed: str) -> int:
    """Convert elapsed text like '1m 31s' or '45s' to total seconds."""
    minutes_match = re.search(r"(?P<minutes>\d+)m", elapsed)
    seconds_match = re.search(r"(?P<seconds>\d+)s", elapsed)
    minutes = int(minutes_match.group("minutes")) if minutes_match else 0
    seconds = int(seconds_match.group("seconds")) if seconds_match else 0
    return (minutes * 60) + seconds


def _to_gib(value: float, unit: str) -> float:
    """Convert MiB/GiB numeric values into GiB."""
    if unit.lower() == "mib":
        return value / 1024
    return value


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
    """Detect whether one log line reports a terminal restore status."""
    lowered = line.lower()
    if any(marker in lowered for marker in _FAILURE_STATUS_MARKERS):
        return "failure"
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


def follow_log_lines(log_path: Path) -> Iterator[str]:
    """Yield lines from a task logfile as they appear."""
    with log_path.open(encoding="utf-8") as handle:
        while True:
            line = handle.readline()
            if line:
                yield line.rstrip("\n")
                continue
            time.sleep(0.2)
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
