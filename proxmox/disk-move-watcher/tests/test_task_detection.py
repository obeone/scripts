"""Tests for active task discovery and disk move task selection."""

from __future__ import annotations

from pathlib import Path

import disk_move_watcher

ACTIVE_MOVE = "UPID:burns:00006472:170DD2EE:6A7B4794:qmmove:123:root@pam: 0"
FINISHED_VNCPROXY = (
    "UPID:burns:00006161:170DC5B0:6A7B4773:vncproxy:123:root@pam: 1 6A7B4778 OK"
)


def test_parse_upid_extracts_node_action_and_vmid() -> None:
    """Split a UPID into its node, worker type and guest id."""
    parsed = disk_move_watcher.parse_upid(ACTIVE_MOVE)

    assert parsed is not None
    assert parsed["node"] == "burns"
    assert parsed["action"] == "qmmove"
    assert parsed["vmid"] == "123"
    assert parsed["status"] == "0"


def test_parse_upid_reads_finished_task_status() -> None:
    """Keep the saved flag of a task that already finished."""
    parsed = disk_move_watcher.parse_upid(FINISHED_VNCPROXY)

    assert parsed is not None
    assert parsed["status"] == "1"


def test_parse_upid_returns_none_for_empty_line() -> None:
    """Return None for a blank line."""
    assert disk_move_watcher.parse_upid("\n") is None


def test_read_active_tasks_keeps_only_running_entries(tmp_path: Path) -> None:
    """Drop tasks whose saved flag marks them as already finished."""
    active_file = tmp_path / "active"
    active_file.write_text(f"{ACTIVE_MOVE}\n{FINISHED_VNCPROXY}\n", encoding="utf-8")

    tasks = disk_move_watcher.read_active_tasks(str(active_file))

    assert [task["action"] for task in tasks] == ["qmmove"]


def test_read_active_tasks_returns_empty_when_index_missing(tmp_path: Path) -> None:
    """Return an empty list when the active tasks index does not exist."""
    assert disk_move_watcher.read_active_tasks(str(tmp_path / "absent")) == []


def test_filter_disk_move_tasks_keeps_vm_and_container_moves() -> None:
    """Keep both the qmmove and move_volume worker types."""
    tasks = [
        {"upid": "UPID:n:1:2:3:qmmove:123:root@pam:", "action": "qmmove", "raw": ""},
        {
            "upid": "UPID:n:1:2:3:move_volume:124:root@pam:",
            "action": "move_volume",
            "raw": "",
        },
    ]

    assert disk_move_watcher.filter_disk_move_tasks(tasks) == tasks


def test_filter_disk_move_tasks_drops_unrelated_worker_types() -> None:
    """Reject migrations, restores and backups, which are other tools' business."""
    tasks = [
        {
            "upid": "UPID:n:1:2:3:qmigrate:123:root@pam:",
            "action": "qmigrate",
            "raw": "",
        },
        {
            "upid": "UPID:n:1:2:3:qmrestore:123:root@pam:",
            "action": "qmrestore",
            "raw": "",
        },
        {"upid": "UPID:n:1:2:3:vzdump::root@pam:", "action": "vzdump", "raw": ""},
    ]

    assert disk_move_watcher.filter_disk_move_tasks(tasks) == []


def test_choose_disk_move_task_auto_selects_the_only_candidate() -> None:
    """Pick the single candidate without any further logic."""
    task = {"upid": "UPID:n:1:2:3:qmmove:123:root@pam:"}

    assert disk_move_watcher.choose_disk_move_task([task]) == task


def test_choose_disk_move_task_prefers_the_most_recent() -> None:
    """Pick the last entry when several moves run at once."""
    first = {"upid": "UPID:n:1:2:3:qmmove:123:root@pam:"}
    second = {"upid": "UPID:n:1:2:4:qmmove:124:root@pam:"}

    assert disk_move_watcher.choose_disk_move_task([first, second]) == second


def test_choose_disk_move_task_honors_explicit_upid() -> None:
    """Select the requested UPID instead of the most recent task."""
    first = {"upid": "UPID:n:1:2:3:qmmove:123:root@pam:"}
    second = {"upid": "UPID:n:1:2:4:qmmove:124:root@pam:"}

    selected = disk_move_watcher.choose_disk_move_task(
        [first, second], upid=first["upid"]
    )

    assert selected == first


def test_choose_disk_move_task_returns_none_for_unknown_upid() -> None:
    """Return None rather than falling back when the UPID does not match."""
    task = {"upid": "UPID:n:1:2:3:qmmove:123:root@pam:"}

    assert disk_move_watcher.choose_disk_move_task([task], upid="UPID:other") is None


def test_choose_disk_move_task_returns_none_without_candidates() -> None:
    """Return None when no disk move task is running."""
    assert disk_move_watcher.choose_disk_move_task([]) is None


def test_format_task_label_summarizes_the_task() -> None:
    """Render a compact label for the task banner and the listing."""
    parsed = disk_move_watcher.parse_upid(ACTIVE_MOVE)

    assert parsed is not None
    assert disk_move_watcher.format_task_label(parsed) == "qmmove vmid=123 node=burns"
