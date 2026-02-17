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


def test_parse_progress_line_with_qmrestore_progress_bytes() -> None:
    """Parse qmrestore progress lines with read bytes and duration seconds."""
    line = "progress 50% (read 2147483648 bytes, zeroes = 10% (214748364 bytes), duration 100 sec)"

    parsed = restore_watcher.parse_progress_line(line)

    assert parsed == (100, 2.0, 4.0)
