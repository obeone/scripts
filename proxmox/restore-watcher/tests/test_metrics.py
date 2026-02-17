"""Tests for restore progress metrics and dashboard text rendering."""

from __future__ import annotations

import math

import restore_watcher


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
