"""Tests for migration progress line parsing.

Every sample line in this module is a real Proxmox rendering, either
observed on a live ``qmigrate`` task log or reproduced from the print
statements in ``PVE::QemuServer::BlockJob``.
"""

from __future__ import annotations

import watcher


def test_parse_progress_line_for_drive_prefixed_block_job() -> None:
    """Parse a drive-prefixed block job line (QEMU < 10) with its duration."""
    line = "drive-scsi0: transferred 5.5 GiB of 252.0 GiB (2.18%) in 1m 31s"

    assert watcher.parse_progress_line(line) == (91, 5.5, 252.0)


def test_parse_progress_line_for_mirror_prefixed_block_job() -> None:
    """Accept the mirror-prefixed job id used by blockdev-mirror (QEMU >= 10)."""
    line = "mirror-scsi0: transferred 0.0 B of 200.0 GiB (0.00%) in 0s"

    assert watcher.parse_progress_line(line) == (0, 0.0, 200.0)


def test_parse_progress_line_handles_mebibytes_without_truncating_to_bytes() -> None:
    """Match "MiB" as a whole unit instead of the shorter "B" alternative."""
    line = "mirror-scsi0: transferred 231.0 MiB of 200.0 GiB (0.11%) in 1s"

    elapsed, transferred_gib, total_gib = watcher.parse_progress_line(line)

    assert elapsed == 1
    assert transferred_gib == 231.0 / 1024
    assert total_gib == 200.0


def test_parse_progress_line_ignores_ready_suffix() -> None:
    """Parse a block job line that appends its readiness state."""
    line = "drive-scsi0: transferred 20.1 GiB of 32.0 GiB (62.81%) in 1m 31s, ready"

    assert watcher.parse_progress_line(line) == (91, 20.1, 32.0)


def test_parse_progress_line_ignores_still_busy_suffix() -> None:
    """Parse a block job line that reports it is still busy."""
    line = (
        "drive-scsi0: transferred 32.0 GiB of 32.0 GiB (100.00%) in 4m 2s, still busy"
    )

    assert watcher.parse_progress_line(line) == (242, 32.0, 32.0)


def test_parse_progress_line_handles_tebibytes_and_a_multi_unit_duration() -> None:
    """Convert TiB values to GiB and parse an hours+minutes+seconds duration."""
    line = "drive-virtio0: transferred 1.2 TiB of 2.0 TiB (60.00%) in 2h 5m 3s"

    elapsed, transferred_gib, total_gib = watcher.parse_progress_line(line)

    assert elapsed == 7503
    assert transferred_gib == 1.2 * 1024
    assert total_gib == 2.0 * 1024


def test_parse_progress_line_returns_none_for_non_matching_lines() -> None:
    """Return None for lines that carry no transfer counters at all."""
    lines = [
        "drive mirror is starting for drive-scsi0",
        "all 'mirror' jobs are ready",
        "TASK OK",
        "migration finished successfully",
    ]

    for line in lines:
        assert watcher.parse_progress_line(line) is None


def test_size_to_gib_covers_every_iec_unit() -> None:
    """Convert each IEC unit PVE::Format::render_bytes can emit into GiB."""
    assert watcher._size_to_gib(1.0, "GiB") == 1.0
    assert watcher._size_to_gib(1024.0, "MiB") == 1.0
    assert watcher._size_to_gib(1024.0, "KiB") == 1 / 1024
    assert watcher._size_to_gib(1.0, "TiB") == 1024.0
    assert watcher._size_to_gib(1.0, "PiB") == 1024.0**2
    assert watcher._size_to_gib(1.0, "B") == 1 / (1024**3)


def test_size_to_gib_returns_zero_for_an_unrecognized_unit() -> None:
    """Fall back to 0.0 GiB instead of raising on an unknown unit."""
    assert watcher._size_to_gib(1.0, "unknown") == 0.0


def test_duration_to_seconds_covers_every_render_duration_form() -> None:
    """Parse every unit combination PVE::Format::render_duration can emit."""
    assert watcher._duration_to_seconds("0s") == 0
    assert watcher._duration_to_seconds("45s") == 45
    assert watcher._duration_to_seconds("1m 31s") == 91
    assert watcher._duration_to_seconds("2h 5m 3s") == 7503
    assert watcher._duration_to_seconds("1d 2h") == 93600
    assert watcher._duration_to_seconds("1w 2d") == 777600
