"""Tests for restore task detection helpers."""

from __future__ import annotations

from pathlib import Path

import restore_watcher


def test_detect_qmrestore_action_as_restore_task() -> None:
    """Detect qmrestore action as restore task."""
    tasks = [
        {
            "upid": "UPID:pve:0001:0001:0001:qmrestore:100:root@pam:",
            "action": "qmrestore",
            "status": "0",
        }
    ]

    restore_tasks = restore_watcher.filter_restore_tasks(tasks)

    assert len(restore_tasks) == 1
    assert restore_tasks[0]["action"] == "qmrestore"


def test_ignore_non_active_tasks(tmp_path: Path) -> None:
    """Ignore tasks with non-active status values."""
    active_file_content = "\n".join(
        [
            "UPID:pve:0001:0001:0001:qmrestore:100:root@pam: 0 1234",
            "UPID:pve:0002:0002:0002:qmrestore:101:root@pam: OK 1235",
            "UPID:pve:0003:0003:0003:qmrestore:102:root@pam:  1236",
        ]
    )

    file_path = _write_active_file(tmp_path, active_file_content)

    tasks = restore_watcher.read_active_tasks(active_path=str(file_path))

    assert len(tasks) == 2
    assert all(task["status"] in {"", "0"} for task in tasks)
    assert tasks[0]["action"] == "qmrestore"


def test_detect_restore_keyword_in_upid_text() -> None:
    """Detect restore markers from raw UPID text keywords."""
    tasks = [
        {
            "upid": "UPID:pve:0001:0001:0001:qmstart:100:root@pam:restore from backup",
            "action": "qmstart",
            "status": "0",
        }
    ]

    restore_tasks = restore_watcher.filter_restore_tasks(tasks)

    assert len(restore_tasks) == 1
    assert "restore" in restore_tasks[0]["upid"]


def _write_active_file(base_path: Path, content: str) -> Path:
    """Write temporary active tasks file used by tests."""
    file_path = base_path / "active-tasks-test.log"
    file_path.write_text(content, encoding="utf-8")
    return file_path
