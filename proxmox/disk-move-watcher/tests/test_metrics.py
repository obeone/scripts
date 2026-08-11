"""Tests for speed, ETA and dashboard rendering."""

from __future__ import annotations

import math

import disk_move_watcher


def test_calculate_eta_and_speed_from_two_points() -> None:
    """Derive speed and ETA from a simple two-point history."""
    points = [(0, 0.0, 10.0), (10, 1.0, 10.0)]

    speed, eta_seconds = disk_move_watcher.calculate_eta_and_speed(points)

    assert speed == 0.1
    assert eta_seconds == 90.0


def test_calculate_eta_and_speed_needs_two_points() -> None:
    """Report an unknown ETA while only one sample is known."""
    speed, eta_seconds = disk_move_watcher.calculate_eta_and_speed([(0, 0.0, 10.0)])

    assert speed == 0.0
    assert math.isinf(eta_seconds)


def test_calculate_eta_and_speed_keeps_previous_speed_on_a_stall() -> None:
    """Keep the last known speed when the transfer makes no progress."""
    points = [(0, 1.0, 10.0), (10, 1.0, 10.0)]

    speed, _ = disk_move_watcher.calculate_eta_and_speed_with_memory(
        points, previous_speed=0.25
    )

    assert speed == 0.25


def test_calculate_eta_and_speed_without_total_has_no_eta() -> None:
    """Report an unknown ETA when the total size is not available."""
    points = [(0, 0.0, None), (10, 1.0, None)]

    speed, eta_seconds = disk_move_watcher.calculate_eta_and_speed(points)

    assert speed == 0.1
    assert math.isinf(eta_seconds)


def test_calculate_eta_is_zero_once_complete() -> None:
    """Clamp the remaining size to zero once the total is reached."""
    points = [(0, 0.0, 10.0), (10, 10.0, 10.0)]

    _, eta_seconds = disk_move_watcher.calculate_eta_and_speed(points)

    assert eta_seconds == 0.0


def test_calculate_total_average_speed_spans_the_whole_window() -> None:
    """Average over the first and last sample, ignoring intermediate jitter."""
    points = [(0, 0.0, 100.0), (10, 5.0, 100.0), (100, 50.0, 100.0)]

    assert disk_move_watcher.calculate_total_average_speed(points) == 0.5


def test_calculate_total_average_speed_needs_forward_progress() -> None:
    """Return zero when no time or no data elapsed between the bounds."""
    assert disk_move_watcher.calculate_total_average_speed([(0, 1.0, 10.0)]) == 0.0
    assert (
        disk_move_watcher.calculate_total_average_speed(
            [(5, 1.0, 10.0), (5, 2.0, 10.0)]
        )
        == 0.0
    )


def test_format_duration_renders_hh_mm_ss() -> None:
    """Render durations as zero-padded hours, minutes and seconds."""
    assert disk_move_watcher.format_duration(0) == "00:00:00"
    assert disk_move_watcher.format_duration(91) == "00:01:31"
    assert disk_move_watcher.format_duration(7503) == "02:05:03"
    assert disk_move_watcher.format_duration(-5) == "00:00:00"


def test_build_tqdm_line_reports_progress_and_throughput() -> None:
    """Render the bar, the sizes, both speeds and the ETA on one line."""
    points = [(0, 0.0, 200.0), (100, 50.0, 200.0)]

    line = disk_move_watcher.build_tqdm_line(
        points,
        speed_gib_s=0.5,
        average_speed_gib_s=0.5,
        eta_seconds=300.0,
        drive="mirror-scsi0",
    )

    assert line.startswith("mirror-scsi0 [")
    assert " 25.0%" in line
    assert "50.00/200.00 GiB" in line
    assert "Now  512.0 MiB/s" in line
    assert "Avg  512.0 MiB/s" in line
    assert "Elapsed 00:01:40" in line
    assert "ETA 00:05:00" in line


def test_build_tqdm_line_without_points_is_still_renderable() -> None:
    """Render an empty bar before the first progress line arrives."""
    line = disk_move_watcher.build_tqdm_line([], 0.0, 0.0, math.inf)

    assert "  0.0%" in line
    assert "ETA n/a" in line


def test_build_tqdm_line_marks_an_unknown_total() -> None:
    """Show a question mark rather than a bogus total size."""
    line = disk_move_watcher.build_tqdm_line([(10, 1.5, None)], 0.0, 0.0, math.inf)

    assert "1.50/     ? GiB" in line


def test_build_tqdm_line_flags_the_waiting_state() -> None:
    """Append a waiting marker when no new log data arrived."""
    line = disk_move_watcher.build_tqdm_line([], 0.0, 0.0, math.inf, waiting=True)

    assert line.endswith("waiting log")


def test_build_tqdm_line_colors_output_on_request() -> None:
    """Emit ANSI escapes only when color is requested."""
    plain = disk_move_watcher.build_tqdm_line([], 0.0, 0.0, math.inf)
    colored = disk_move_watcher.build_tqdm_line([], 0.0, 0.0, math.inf, color=True)

    assert "\033[" not in plain
    assert "\033[" in colored


def test_visible_length_discounts_ansi_escapes() -> None:
    """Count only printable characters when measuring a colored string."""
    assert disk_move_watcher.visible_length("abc") == 3
    assert disk_move_watcher.visible_length("\033[32mabc\033[0m") == 3


def test_clip_to_width_leaves_short_text_alone() -> None:
    """Return the text untouched when it already fits."""
    assert disk_move_watcher.clip_to_width("abc", 10) == "abc"


def test_clip_to_width_cuts_on_visible_columns() -> None:
    """Cut on printable columns, not on raw string length."""
    assert disk_move_watcher.clip_to_width("abcdef", 3) == "abc"


def test_clip_to_width_keeps_escapes_and_closes_them() -> None:
    """Keep color escapes while clipping, then terminate the color."""
    clipped = disk_move_watcher.clip_to_width("\033[32mabcdef\033[0m", 3)

    assert clipped == "\033[32mabc\033[0m"


def test_build_tqdm_line_fits_the_requested_width() -> None:
    """Never exceed the width budget, whatever the terminal size."""
    points = [(0, 0.0, 200.0), (100, 50.0, 200.0)]

    for width in (60, 80, 100, 120, 200):
        line = disk_move_watcher.build_tqdm_line(
            points,
            speed_gib_s=0.5,
            average_speed_gib_s=0.5,
            eta_seconds=300.0,
            drive="mirror-scsi0",
            width=width,
        )

        assert disk_move_watcher.visible_length(line) <= width


def test_build_tqdm_line_shrinks_the_bar_before_the_metrics() -> None:
    """Trade bar width for readable metrics when the terminal is narrow."""
    points = [(0, 0.0, 200.0), (100, 50.0, 200.0)]
    kwargs = {
        "speed_gib_s": 0.5,
        "average_speed_gib_s": 0.5,
        "eta_seconds": 300.0,
        "drive": "mirror-scsi0",
    }

    wide = disk_move_watcher.build_tqdm_line(points, width=200, **kwargs)
    narrow = disk_move_watcher.build_tqdm_line(points, width=100, **kwargs)

    assert wide.count("=") + wide.count(".") > narrow.count("=") + narrow.count(".")
    # The ETA is the field operators actually watch, so it must survive.
    assert "ETA 00:05:00" in narrow


def test_build_tqdm_line_keeps_a_usable_bar_when_very_narrow() -> None:
    """Never shrink the bar below its floor, clipping the line instead."""
    line = disk_move_watcher.build_tqdm_line(
        [(0, 0.0, 200.0)], 0.0, 0.0, math.inf, width=20
    )

    assert disk_move_watcher.visible_length(line) <= 20


def test_build_dashboard_lines_fits_every_line_in_the_width() -> None:
    """Clip the tailed log lines to the width as well as the status line."""
    lines = disk_move_watcher.build_dashboard_lines(
        [(10, 1.0, 10.0), (20, 2.0, 10.0)],
        speed_gib_s=0.1,
        average_speed_gib_s=0.08,
        eta_seconds=80.0,
        recent_logs=["x" * 300],
        width=90,
    )

    for line in lines:
        assert disk_move_watcher.visible_length(line) <= 90


def test_build_dashboard_lines_keeps_only_five_recent_logs() -> None:
    """Render only the five most recent log lines under the status line."""
    points = [(10, 1.0, 10.0), (20, 2.0, 10.0)]
    logs = [f"log-{index}" for index in range(8)]

    lines = disk_move_watcher.build_dashboard_lines(
        points,
        speed_gib_s=0.1,
        average_speed_gib_s=0.08,
        eta_seconds=80.0,
        recent_logs=logs,
    )

    assert len(lines) == 6
    assert lines[1].endswith("log-3")
    assert lines[-1].endswith("log-7")


def test_render_dashboard_rewrites_in_place_on_a_tty() -> None:
    """Move the cursor up by the previous line count when on a TTY."""

    class _TtyStream:
        """Minimal writable stream that claims to be a TTY."""

        def __init__(self) -> None:
            self.chunks: list[str] = []

        def write(self, value: str) -> int:
            """Record one written chunk."""
            self.chunks.append(value)
            return len(value)

        def flush(self) -> None:
            """Satisfy the stream interface."""

        def isatty(self) -> bool:
            """Pretend to be an interactive terminal."""
            return True

    stream = _TtyStream()

    written = disk_move_watcher.render_dashboard(stream, ["a", "b"], 2, True)

    assert written == 2
    assert "\033[2A" in stream.chunks[0]


def test_render_dashboard_appends_when_not_a_tty() -> None:
    """Never emit cursor movement when the output is redirected."""
    from io import StringIO

    stream = StringIO()

    written = disk_move_watcher.render_dashboard(stream, ["a", "b"], 2, False)

    assert written == 2
    assert stream.getvalue() == "a\nb\n"
