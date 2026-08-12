"""Tests for restore progress metrics and dashboard text rendering."""

from __future__ import annotations

import math

import restore_watcher


def test_visible_length_discounts_ansi_escapes() -> None:
    """Count only printable characters when measuring a colored string."""
    assert restore_watcher.visible_length("abc") == 3
    assert restore_watcher.visible_length("\033[32mabc\033[0m") == 3


def test_clip_to_width_cuts_on_visible_columns() -> None:
    """Cut on printable columns, not on raw string length."""
    assert restore_watcher.clip_to_width("abc", 10) == "abc"
    assert restore_watcher.clip_to_width("abcdef", 3) == "abc"


def test_clip_to_width_keeps_escapes_and_closes_them() -> None:
    """Keep color escapes while clipping, then terminate the color."""
    assert (
        restore_watcher.clip_to_width("\033[32mabcdef\033[0m", 3)
        == "\033[32mabc\033[0m"
    )


def test_build_tqdm_line_fits_the_requested_width() -> None:
    """Never exceed the width budget, whatever the terminal size.

    The in-place redraw moves the cursor up by a count of screen rows, so a
    wrapped status line desynchronizes every following frame.
    """
    points = [(0, 0.0, 200.0), (100, 50.0, 200.0)]

    for width in (40, 60, 80, 100, 120, 200):
        line = restore_watcher.build_tqdm_line(
            points,
            speed_gib_s=0.5,
            average_speed_gib_s=0.5,
            eta_seconds=300.0,
            width=width,
        )

        assert restore_watcher.visible_length(line) <= width


def test_build_tqdm_line_keeps_the_eta_when_narrow() -> None:
    """Drop the least useful metrics before the completion ratio and the ETA."""
    points = [(0, 0.0, 200.0), (100, 50.0, 200.0)]

    line = restore_watcher.build_tqdm_line(points, 0.5, 0.5, 300.0, width=80)

    assert "ETA 00:05:00" in line
    assert " 25.0%" in line


def test_build_dashboard_lines_fits_every_line_in_the_width() -> None:
    """Clip the tailed log lines to the width as well as the status line."""
    lines = restore_watcher.build_dashboard_lines(
        [(10, 1.0, 10.0), (20, 2.0, 10.0)],
        speed_gib_s=0.1,
        average_speed_gib_s=0.08,
        eta_seconds=80.0,
        recent_logs=["x" * 300],
        width=90,
    )

    for line in lines:
        assert restore_watcher.visible_length(line) <= 90


def test_calculate_eta_and_speed_with_less_than_two_points() -> None:
    """Return zero speed and infinite ETA with fewer than two points."""
    speed, eta_seconds = restore_watcher.calculate_eta_and_speed([(10, 1.0, 5.0)])

    assert speed == 0.0
    assert math.isinf(eta_seconds)


def test_calculate_eta_and_speed_with_known_total_and_positive_delta() -> None:
    """Compute positive speed and finite ETA when total is known."""
    points = [(10, 2.0, 10.0), (20, 4.0, 10.0)]

    speed, eta_seconds = restore_watcher.calculate_eta_and_speed(points)

    assert speed > 0
    assert eta_seconds == 30.0


def test_calculate_eta_and_speed_with_unknown_total() -> None:
    """Keep ETA infinite when total size is unknown."""
    points = [(10, 10.0, None), (20, 20.0, None)]

    speed, eta_seconds = restore_watcher.calculate_eta_and_speed(points)

    assert speed > 0
    assert math.isinf(eta_seconds)


def test_build_metrics_line_formats_progress_speed_and_eta() -> None:
    """Render a compact metrics line for known total progress."""
    points = [(10, 2.0, 10.0), (20, 4.0, 10.0)]

    line = restore_watcher.build_metrics_line(points)

    assert "Progress: 40.0% (4.00/10.00 GiB)" in line
    assert "Speed: 0.20 GiB/s" in line
    assert "ETA: 00:00:30" in line


def test_build_metrics_line_handles_unknown_total_without_crashing() -> None:
    """Render unknown-total progress without raising and with ETA unavailable."""
    points = [(20, 37.5, None), (45, 50.0, None)]

    line = restore_watcher.build_metrics_line(points)

    assert "Progress: 50.0%" in line
    assert "Speed: 0.50 %/s" in line
    assert "ETA: n/a" in line


def test_calculate_eta_with_memory_keeps_previous_speed_on_stall() -> None:
    """Keep previous speed when no positive delta appears in latest points."""
    points = [(10, 2.0, 10.0), (20, 2.0, 10.0)]

    speed, eta_seconds = restore_watcher.calculate_eta_and_speed_with_memory(
        points, previous_speed=0.2
    )

    assert speed == 0.2
    assert eta_seconds == 40.0


def test_calculate_total_average_speed_from_first_and_last_points() -> None:
    """Compute average speed over full elapsed monitoring window."""
    points = [(10, 2.0, 10.0), (20, 4.0, 10.0), (30, 8.0, 10.0)]

    average_speed = restore_watcher.calculate_total_average_speed(points)

    assert average_speed == 0.3


def test_build_tqdm_line_includes_elapsed_avg_and_current_speed() -> None:
    """Render elapsed time, current throughput, and total average throughput."""
    points = [(10, 2.0, 10.0), (20, 4.0, 10.0), (30, 8.0, 10.0)]

    line = restore_watcher.build_tqdm_line(
        points,
        speed_gib_s=0.4,
        average_speed_gib_s=0.3,
        eta_seconds=5.0,
        waiting=False,
    )

    assert "Now" in line
    assert "Avg" in line
    assert "Elapsed" in line
    assert "00:00:30" in line
