"""Tests for task logfile resolution."""

from __future__ import annotations

from pathlib import Path

import watcher

# Real UPID of a qmigrate task observed on a Proxmox 8 node, whose log file
# lives in /var/log/pve/tasks/4/ -- the *last* hex digit of the starttime
# field (5th colon-separated field of the UPID), not its first digit.
LIVE_UPID = "UPID:burns:00006472:170DD2EE:6A7B4794:qmigrate:123:root@pam:"


def _write_log(tasks_root: Path, folder: str, upid: str) -> Path:
    """Create an empty task log file under one shard folder."""
    logfile = tasks_root / folder / upid
    logfile.parent.mkdir(parents=True, exist_ok=True)
    logfile.write_text("", encoding="utf-8")
    return logfile


def test_find_task_logfile_uses_last_starttime_digit(tmp_path: Path) -> None:
    """Resolve the log through the shard folder Proxmox actually writes to."""
    expected = _write_log(tmp_path, "4", LIVE_UPID)

    found = watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path)

    assert found == str(expected)


def test_find_task_logfile_does_not_use_the_first_starttime_digit(
    tmp_path: Path,
) -> None:
    """Do not shard by the first digit of starttime -- that was the bug.

    starttime is 6A7B4794: a broken implementation keyed the folder on its
    first digit ("6") instead of its last ("4").
    """
    decoy = _write_log(tmp_path, "6", LIVE_UPID)
    expected = _write_log(tmp_path, "4", LIVE_UPID)

    found = watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path)

    assert found == str(expected)
    assert found != str(decoy)


def test_find_task_logfile_falls_back_to_scanning_all_shard_folders(
    tmp_path: Path,
) -> None:
    """Scan the remaining 16 shard folders when the expected one is empty."""
    expected = _write_log(tmp_path, "B", LIVE_UPID)

    found = watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path)

    assert found == str(expected)


def test_find_task_logfile_returns_none_when_absent(tmp_path: Path) -> None:
    """Return None when no shard folder holds the log."""
    assert watcher.find_task_logfile(LIVE_UPID, tasks_root=tmp_path) is None


def test_find_task_logfile_returns_none_for_a_too_short_upid(tmp_path: Path) -> None:
    """Return None instead of raising when the UPID has no starttime field."""
    assert watcher.find_task_logfile("UPID:burns:1:2", tasks_root=tmp_path) is None
