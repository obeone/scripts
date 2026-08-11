"""Tests for disk move progress line parsing.

Every sample line in this module is a real Proxmox rendering, either observed
on a live ``qmmove`` task log or reproduced from the print statements in
``PVE::QemuServer::BlockJob`` and ``PVE::QemuImage``.
"""

from __future__ import annotations

import disk_move_watcher


def test_parse_progress_line_for_online_block_job() -> None:
    """Parse a drive-prefixed block job line with its rendered duration."""
    line = "drive-scsi0: transferred 5.5 GiB of 252.0 GiB (2.18%) in 1m 31s"

    parsed = disk_move_watcher.parse_progress_line(line)

    assert parsed == (91, 5.5, 252.0, "drive-scsi0")


def test_parse_progress_line_for_blockdev_mirror_job_prefix() -> None:
    """Accept the mirror-prefixed job id used from QEMU 10.0 onwards."""
    line = "mirror-scsi0: transferred 231.0 MiB of 200.0 GiB (0.11%) in 1s"

    elapsed, transferred_gib, total_gib, drive = disk_move_watcher.parse_progress_line(
        line
    )

    assert elapsed == 1
    assert transferred_gib == 231.0 / 1024
    assert total_gib == 200.0
    assert drive == "mirror-scsi0"


def test_parse_progress_line_ignores_ready_suffix() -> None:
    """Parse a block job line that appends its readiness state."""
    line = "drive-scsi0: transferred 20.1 GiB of 32.0 GiB (62.81%) in 1m 31s, ready"

    parsed = disk_move_watcher.parse_progress_line(line)

    assert parsed == (91, 20.1, 32.0, "drive-scsi0")


def test_parse_progress_line_ignores_still_busy_suffix() -> None:
    """Parse a block job line that reports it is still busy."""
    line = (
        "drive-scsi0: transferred 32.0 GiB of 32.0 GiB (100.00%) in 4m 2s, still busy"
    )

    parsed = disk_move_watcher.parse_progress_line(line)

    assert parsed == (242, 32.0, 32.0, "drive-scsi0")


def test_parse_progress_line_for_offline_convert_has_no_elapsed() -> None:
    """Report a None elapsed time when the log line carries no duration."""
    line = "transferred 512.0 MiB of 32.0 GiB (1.56%)"

    elapsed, transferred_gib, total_gib, drive = disk_move_watcher.parse_progress_line(
        line
    )

    assert elapsed is None
    assert transferred_gib == 512.0 / 1024
    assert total_gib == 32.0
    assert drive is None


def test_parse_progress_line_handles_bytes_unit() -> None:
    """Accept a bare bytes unit without matching it inside MiB or GiB."""
    line = "mirror-scsi0: transferred 0.0 B of 200.0 GiB (0.00%) in 0s"

    assert disk_move_watcher.parse_progress_line(line) == (
        0,
        0.0,
        200.0,
        "mirror-scsi0",
    )


def test_parse_progress_line_handles_tebibytes() -> None:
    """Convert TiB values up to GiB."""
    line = "drive-virtio0: transferred 1.2 TiB of 2.0 TiB (60.00%) in 2h 5m 3s"

    elapsed, transferred_gib, total_gib, drive = disk_move_watcher.parse_progress_line(
        line
    )

    assert elapsed == 7503
    assert transferred_gib == 1.2 * 1024
    assert total_gib == 2.0 * 1024
    assert drive == "drive-virtio0"


def test_parse_progress_line_reports_none_total_for_zero_size() -> None:
    """Return a None total rather than a zero that would break the ETA."""
    line = "transferred 0.0 B of 0.0 B (0.00%)"

    assert disk_move_watcher.parse_progress_line(line) == (None, 0.0, None, None)


def test_parse_progress_line_returns_none_for_non_matching_line() -> None:
    """Return None when the line carries no transfer counters."""
    lines = [
        "drive mirror is starting for drive-scsi0",
        "all 'mirror' jobs are ready",
        "TASK OK",
        "Formatting '/mnt/nodes/images/123/vm-123-disk-0.raw', fmt=raw size=214748364800",
    ]

    for line in lines:
        assert disk_move_watcher.parse_progress_line(line) is None


def test_parse_size_to_gib_covers_iec_units() -> None:
    """Convert every supported IEC unit into GiB."""
    assert disk_move_watcher.parse_size_to_gib(1.0, "GiB") == 1.0
    assert disk_move_watcher.parse_size_to_gib(1024.0, "MiB") == 1.0
    assert disk_move_watcher.parse_size_to_gib(1024.0, "KiB") == 1 / 1024
    assert disk_move_watcher.parse_size_to_gib(1.0, "TiB") == 1024.0
    assert disk_move_watcher.parse_size_to_gib(1.0, "PiB") == 1024.0**2
    assert disk_move_watcher.parse_size_to_gib(1.0, "unknown") == 0.0


def test_parse_duration_seconds_covers_render_duration_forms() -> None:
    """Parse every unit combination PVE::Format::render_duration can emit."""
    assert disk_move_watcher.parse_duration_seconds("0s") == 0
    assert disk_move_watcher.parse_duration_seconds("45s") == 45
    assert disk_move_watcher.parse_duration_seconds("1m 31s") == 91
    assert disk_move_watcher.parse_duration_seconds("2h 5m 3s") == 7503
    assert disk_move_watcher.parse_duration_seconds("1d 2h") == 93600
    assert disk_move_watcher.parse_duration_seconds("1w 2d") == 777600


def test_parse_duration_seconds_without_recognizable_units() -> None:
    """Return None when no duration unit is present."""
    assert disk_move_watcher.parse_duration_seconds(None) is None
    assert disk_move_watcher.parse_duration_seconds("") is None
    assert disk_move_watcher.parse_duration_seconds("later") is None
