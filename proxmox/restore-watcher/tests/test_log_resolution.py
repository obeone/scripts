"""Tests for task log file resolution."""

from __future__ import annotations

from pathlib import Path

import restore_watcher


def test_find_task_logfile_uses_last_starttime_hex_folder(tmp_path: Path) -> None:
    """Resolve the log through the shard folder Proxmox actually writes to.

    The folder is the last hex digit of the starttime field, per
    substr($starttime, 7, 1) in PVE::RESTEnvironment::fork_worker.
    """
    upid = "UPID:node:00000001:00000000:A1234567:qmrestore:101:root@pam:"
    log_path = tmp_path / "7" / upid
    log_path.parent.mkdir(parents=True)
    log_path.write_text("task log", encoding="utf-8")

    resolved = restore_watcher.find_task_logfile(upid, tasks_root=tmp_path)

    assert resolved == log_path


def test_find_task_logfile_does_not_use_the_first_starttime_digit(
    tmp_path: Path,
) -> None:
    """Prefer the correct shard over one keyed on the first starttime digit."""
    upid = "UPID:node:00000001:00000000:A1234567:qmrestore:101:root@pam:"
    decoy = tmp_path / "A" / upid
    decoy.parent.mkdir(parents=True)
    decoy.write_text("task log", encoding="utf-8")
    expected = tmp_path / "7" / upid
    expected.parent.mkdir(parents=True)
    expected.write_text("task log", encoding="utf-8")

    resolved = restore_watcher.find_task_logfile(upid, tasks_root=tmp_path)

    assert resolved == expected
    assert resolved != decoy


def test_find_task_logfile_scans_all_hex_folders_when_expected_missing(
    tmp_path: Path,
) -> None:
    """Fallback scan should find file in another archive subfolder."""
    upid = "UPID:node:00000001:00000000:B1234567:qmrestore:101:root@pam:"
    fallback_path = tmp_path / "F" / upid
    fallback_path.parent.mkdir(parents=True)
    fallback_path.write_text("task log", encoding="utf-8")

    resolved = restore_watcher.find_task_logfile(upid, tasks_root=tmp_path)

    assert resolved == fallback_path


def test_find_task_logfile_returns_none_for_malformed_upid(tmp_path: Path) -> None:
    """Return None when the UPID format does not contain a valid PSTART."""
    resolved = restore_watcher.find_task_logfile("UPID:node:bad", tasks_root=tmp_path)

    assert resolved is None


def test_find_task_logfile_rejects_short_upid_even_if_file_exists(
    tmp_path: Path,
) -> None:
    """Reject short UPIDs that do not match the expected segment count."""
    short_upid = "UPID:node:1:2:A1234567"
    bogus_path = tmp_path / "A" / short_upid
    bogus_path.parent.mkdir(parents=True)
    bogus_path.write_text("task log", encoding="utf-8")

    resolved = restore_watcher.find_task_logfile(short_upid, tasks_root=tmp_path)

    assert resolved is None
