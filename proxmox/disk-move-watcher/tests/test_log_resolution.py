"""Tests for task logfile resolution."""

from __future__ import annotations

from pathlib import Path

import disk_move_watcher

# Real UPID of a qmmove task observed on a Proxmox 8 node, whose log file lives
# in /var/log/pve/tasks/4/ — the last hex digit of the starttime field.
LIVE_UPID = "UPID:burns:00006472:170DD2EE:6A7B4794:qmmove:123:root@pam:"


def _write_log(tasks_root: Path, folder: str, upid: str) -> Path:
    """Create an empty task log file under one shard folder."""
    logfile = tasks_root / folder / upid
    logfile.parent.mkdir(parents=True, exist_ok=True)
    logfile.write_text("", encoding="utf-8")
    return logfile


def test_find_task_logfile_uses_last_starttime_digit(tmp_path: Path) -> None:
    """Resolve the log through the shard folder Proxmox actually writes to."""
    expected = _write_log(tmp_path, "4", LIVE_UPID)

    found = disk_move_watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path)

    assert found == expected


def test_find_task_logfile_does_not_use_the_pstart_field(tmp_path: Path) -> None:
    """Do not look the log up under the first digit of pstart."""
    # pstart is 170DD2EE, so a naive implementation would look into folder "1".
    decoy = _write_log(tmp_path, "1", LIVE_UPID)
    expected = _write_log(tmp_path, "4", LIVE_UPID)

    found = disk_move_watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path)

    assert found == expected
    assert found != decoy


def test_find_task_logfile_falls_back_to_other_folders(tmp_path: Path) -> None:
    """Scan the remaining shard folders when the expected one is empty."""
    expected = _write_log(tmp_path, "B", LIVE_UPID)

    found = disk_move_watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path)

    assert found == expected


def test_find_task_logfile_returns_none_when_absent(tmp_path: Path) -> None:
    """Return None when no shard folder holds the log."""
    assert disk_move_watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path) is None


def test_find_task_logfile_rejects_malformed_upid(tmp_path: Path) -> None:
    """Reject strings that are not full UPIDs."""
    assert (
        disk_move_watcher.find_task_logfile("not-a-upid", tasks_root=tmp_path) is None
    )
    assert (
        disk_move_watcher.find_task_logfile("UPID:burns:1:2:3", tasks_root=tmp_path)
        is None
    )


def test_find_task_logfile_rejects_non_hex_starttime(tmp_path: Path) -> None:
    """Reject a UPID whose starttime field is not eight hex digits."""
    upid = "UPID:burns:00006472:170DD2EE:zzzz:qmmove:123:root@pam:"

    assert disk_move_watcher.find_task_logfile(upid, tasks_root=tmp_path) is None


def test_resolve_disk_move_logfile_from_task(tmp_path: Path) -> None:
    """Resolve the log file straight from a parsed task entry."""
    expected = _write_log(tmp_path, "4", LIVE_UPID)

    found = disk_move_watcher.resolve_disk_move_logfile(
        {"upid": LIVE_UPID}, tasks_root=tmp_path
    )

    assert found == expected


def test_resolve_disk_move_logfile_without_upid(tmp_path: Path) -> None:
    """Return None when the task entry carries no UPID."""
    assert disk_move_watcher.resolve_disk_move_logfile({}, tasks_root=tmp_path) is None
