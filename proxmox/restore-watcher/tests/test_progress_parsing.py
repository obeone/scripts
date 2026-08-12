"""Tests for restore progress line parsing."""

from __future__ import annotations

import restore_watcher


def test_parse_progress_line_with_gib_values() -> None:
    """Parse GiB progress values and elapsed duration."""
    line = "transferred 5.5 GiB of 252.0 GiB (2.2%) in 1m 31s"

    parsed = restore_watcher.parse_progress_line(line)

    assert parsed == (91, 5.5, 252.0)


def test_parse_progress_line_with_mib_values_converts_to_gib() -> None:
    """Convert MiB values to GiB before returning parsed progress."""
    line = "transferred 1024 MiB of 2048 MiB (50%) in 2m 0s"

    parsed = restore_watcher.parse_progress_line(line)

    assert parsed == (120, 1.0, 2.0)


def test_parse_progress_line_with_percent_only_and_elapsed_time() -> None:
    """Handle percent-only lines where total size is not provided."""
    line = "transferred 37.5% in 45s"

    parsed = restore_watcher.parse_progress_line(line)

    assert parsed == (45, 37.5, None)


def test_parse_progress_line_returns_none_for_non_matching_line() -> None:
    """Return None when line does not match any progress pattern."""
    parsed = restore_watcher.parse_progress_line("starting VM restore task")

    assert parsed is None


def test_parse_progress_line_with_hour_bearing_duration() -> None:
    """Parse a duration that includes hours.

    PVE::Format::render_duration switches to "2h 5m 3s" past the hour mark. The
    duration grammar used to accept minutes and seconds only, so long restores
    lost progress parsing entirely at the one hour boundary.
    """
    line = "transferred 100.0 GiB of 200.0 GiB (50%) in 2h 5m 3s"

    assert restore_watcher.parse_progress_line(line) == (7503, 100.0, 200.0)


def test_parse_progress_line_elapsed_stays_monotonic_across_the_hour() -> None:
    """Keep elapsed time increasing when the duration gains an hours field."""
    before = restore_watcher.parse_progress_line(
        "transferred 1.0 GiB of 200.0 GiB (0.5%) in 59m 59s"
    )
    after = restore_watcher.parse_progress_line(
        "transferred 2.0 GiB of 200.0 GiB (1%) in 1h 0m 1s"
    )

    assert before is not None
    assert after is not None
    assert after[0] > before[0]


def test_parse_progress_line_with_day_bearing_duration() -> None:
    """Parse the compact form render_duration emits for very long transfers."""
    line = "transferred 1.0 TiB of 4.0 TiB (25%) in 1d 2h"

    assert restore_watcher.parse_progress_line(line) == (93600, 1024.0, 4096.0)


def test_parse_progress_line_with_bytes_and_kib_units() -> None:
    """Accept every IEC unit render_bytes can emit, not just MiB and GiB."""
    line = "transferred 0.0 B of 2.0 TiB (0%) in 1s"

    assert restore_watcher.parse_progress_line(line) == (1, 0.0, 2048.0)


def test_parse_progress_line_with_qmrestore_progress_bytes() -> None:
    """Parse qmrestore progress lines with read bytes and duration seconds."""
    line = "progress 50% (read 2147483648 bytes, zeroes = 10% (214748364 bytes), duration 100 sec)"

    parsed = restore_watcher.parse_progress_line(line)

    assert parsed == (100, 2.0, 4.0)
