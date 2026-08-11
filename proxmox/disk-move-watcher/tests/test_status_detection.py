"""Tests for milestone detection, the monitoring loop and the CLI entry point."""

from __future__ import annotations

from collections.abc import Iterator
from io import StringIO
from pathlib import Path

import pytest

import disk_move_watcher

TASK = {
    "upid": "UPID:burns:00006472:170DD2EE:6A7B4794:qmmove:123:root@pam:",
    "node": "burns",
    "action": "qmmove",
    "vmid": "123",
    "status": "0",
    "raw": "UPID:burns:00006472:170DD2EE:6A7B4794:qmmove:123:root@pam: 0",
}


class _SteppingClock:
    """Monotonic clock stub advancing by a fixed step on every call."""

    def __init__(self, step: float = 1.0) -> None:
        self.step = step
        self.value = 0.0

    def __call__(self) -> float:
        """Return the current value, then advance it."""
        current = self.value
        self.value += self.step
        return current


def test_detect_terminal_status_for_task_ok() -> None:
    """Treat the TASK OK epilogue as a success."""
    assert disk_move_watcher.detect_terminal_status("TASK OK") == "success"


def test_detect_terminal_status_for_task_error() -> None:
    """Treat the TASK ERROR epilogue as a failure."""
    line = "TASK ERROR: storage migration failed: mirroring error"

    assert disk_move_watcher.detect_terminal_status(line) == "failure"


def test_detect_terminal_status_for_task_warnings() -> None:
    """Treat TASK WARNINGS as terminal, since TASK OK never follows it."""
    assert disk_move_watcher.detect_terminal_status("TASK WARNINGS: 1") == "warnings"


def test_detect_terminal_status_ignores_per_job_completion() -> None:
    """Never end the task on a single block job completing."""
    line = "drive-scsi0: Completed successfully."

    assert disk_move_watcher.detect_terminal_status(line) is None


def test_detect_terminal_status_for_running_lines() -> None:
    """Return None for lines emitted while the move is still running."""
    lines = [
        "drive mirror is starting for drive-scsi0",
        "mirror-scsi0: transferred 0.0 B of 200.0 GiB (0.00%) in 0s",
        "all 'mirror' jobs are ready",
    ]

    for line in lines:
        assert disk_move_watcher.detect_terminal_status(line) is None


def test_detect_milestone_recognizes_move_steps() -> None:
    """Recognize the milestone lines a disk move prints around the transfer."""
    cases = {
        "copying volume 'thin_pool:vm-123-disk-1' from current storage 'thin_pool'"
        " to target storage 'nodes-gluster'": "copying volume",
        "create full clone of drive scsi0 (thin_pool:vm-123-disk-1)": (
            "create full clone of drive"
        ),
        "Formatting '/mnt/nodes/images/123/vm-123-disk-0.raw', fmt=raw": "formatting '",
        "allocated target volume 'nodes-gluster:123/vm-123-disk-0.raw'": (
            "allocated target volume"
        ),
        "drive mirror is starting for drive-scsi0": "drive mirror is starting",
        "all 'mirror' jobs are ready": "all 'mirror' jobs are ready",
        "drive-scsi0: Completing block job...": "completing block job",
    }

    for line, expected in cases.items():
        assert disk_move_watcher.detect_milestone(line) == expected


def test_detect_milestone_returns_none_for_progress_lines() -> None:
    """Do not classify a progress line as a milestone."""
    line = "mirror-scsi0: transferred 231.0 MiB of 200.0 GiB (0.11%) in 1s"

    assert disk_move_watcher.detect_milestone(line) is None


def test_collect_monitoring_data_stops_on_terminal_status() -> None:
    """Collect progress points and stop as soon as the task ends."""
    lines = [
        "drive-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s",
        "drive-scsi0: transferred 2.0 GiB of 10.0 GiB (20.00%) in 20s",
        "TASK OK",
        "drive-scsi0: transferred 3.0 GiB of 10.0 GiB (30.00%) in 30s",
    ]

    points, status = disk_move_watcher.collect_monitoring_data(lines)

    assert status == "success"
    assert points == [(10, 1.0, 10.0), (20, 2.0, 10.0)]


def test_collect_monitoring_data_stamps_offline_samples_from_the_clock() -> None:
    """Stamp elapsed times from the clock when the log reports none."""
    lines = [
        "transferred 1.0 GiB of 32.0 GiB (3.12%)",
        "transferred 2.0 GiB of 32.0 GiB (6.25%)",
        "TASK OK",
    ]

    points, status = disk_move_watcher.collect_monitoring_data(
        lines, now_fn=_SteppingClock(step=2.0)
    )

    assert status == "success"
    assert [point[1] for point in points] == [1.0, 2.0]
    assert [point[2] for point in points] == [32.0, 32.0]
    # Elapsed times come from the clock, so they must simply move forward.
    assert points[0][0] > 0
    assert points[1][0] > points[0][0]


def test_collect_monitoring_data_resets_history_when_the_drive_changes() -> None:
    """Drop the previous drive's history so speed and ETA stay meaningful."""
    lines = [
        "drive-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s",
        "drive-scsi0: transferred 9.0 GiB of 10.0 GiB (90.00%) in 20s",
        "drive-scsi1: transferred 0.5 GiB of 4.0 GiB (12.50%) in 5s",
        "TASK OK",
    ]

    points, status = disk_move_watcher.collect_monitoring_data(lines)

    assert status == "success"
    assert points == [(5, 0.5, 4.0)]


def test_collect_monitoring_data_keeps_history_for_a_stable_drive() -> None:
    """Never reset history while the same drive keeps reporting."""
    lines = [
        "mirror-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s",
        "mirror-scsi0: transferred 2.0 GiB of 10.0 GiB (20.00%) in 20s",
        "TASK OK",
    ]

    points, _ = disk_move_watcher.collect_monitoring_data(lines)

    assert len(points) == 2


def test_collect_monitoring_data_reports_idle_timeout() -> None:
    """Report an idle timeout when the log stops without an epilogue."""
    lines = ["drive-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s"]

    points, status = disk_move_watcher.collect_monitoring_data(lines)

    assert status == "idle-timeout"
    assert points == [(10, 1.0, 10.0)]


def test_collect_monitoring_data_handles_keyboard_interrupt() -> None:
    """Return the interrupted status when the operator presses Ctrl+C."""

    def _interrupting_lines() -> Iterator[str]:
        """Yield one progress line, then interrupt."""
        yield "drive-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s"
        raise KeyboardInterrupt

    points, status = disk_move_watcher.collect_monitoring_data(_interrupting_lines())

    assert status == "interrupted"
    assert points == [(10, 1.0, 10.0)]


def test_collect_monitoring_data_prints_live_updates() -> None:
    """Render the dashboard whenever a progress line is parsed."""
    lines = [
        "drive-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s",
        "drive-scsi0: transferred 2.0 GiB of 10.0 GiB (20.00%) in 20s",
        "TASK OK",
    ]
    output_stream = StringIO()

    points, status = disk_move_watcher.collect_monitoring_data(
        lines,
        output_stream=output_stream,
        update_interval_seconds=60.0,
        now_fn=lambda: 0.0,
    )

    output = output_stream.getvalue()
    assert status == "success"
    assert points[-1] == (20, 2.0, 10.0)
    assert "drive-scsi0 [" in output
    assert "MiB/s" in output


def test_collect_monitoring_data_prints_heartbeat_without_progress() -> None:
    """Render a waiting heartbeat when no progress line arrives."""
    lines = [
        "drive mirror is starting for drive-scsi0",
        "TASK OK",
    ]
    output_stream = StringIO()

    _, status = disk_move_watcher.collect_monitoring_data(
        lines,
        output_stream=output_stream,
        update_interval_seconds=1.0,
        now_fn=_SteppingClock(step=2.0),
    )

    assert status == "success"
    assert "waiting log" in output_stream.getvalue()


def test_monitor_disk_move_task_reports_missing_log(tmp_path: Path) -> None:
    """Report log-missing when the task log cannot be resolved."""
    points, status = disk_move_watcher.monitor_disk_move_task(TASK, tasks_root=tmp_path)

    assert points == []
    assert status == "log-missing"


def test_map_final_status_message_covers_every_status() -> None:
    """Map each known status to its summary line, and anything else to unknown."""
    assert disk_move_watcher.map_final_status_message("success").endswith("success")
    assert (
        disk_move_watcher.map_final_status_message("warnings")
        == "Final status: success with warnings"
    )
    assert disk_move_watcher.map_final_status_message("failure").endswith("failure")
    assert disk_move_watcher.map_final_status_message("no-task").endswith("no-task")
    assert disk_move_watcher.map_final_status_message(None).endswith("unknown")
    assert disk_move_watcher.map_final_status_message("nonsense").endswith("unknown")


def test_main_prints_final_summary_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Always print one final summary line at the end of a run."""
    logfile = tmp_path / "4" / TASK["upid"]
    logfile.parent.mkdir(parents=True)
    logfile.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        disk_move_watcher, "read_active_tasks", lambda active_path=None: [TASK]
    )
    monkeypatch.setattr(
        disk_move_watcher, "find_task_logfile", lambda upid, tasks_root=None: logfile
    )
    monkeypatch.setattr(
        disk_move_watcher,
        "follow_log_lines",
        lambda log_path: iter(
            [
                "mirror-scsi0: transferred 1.0 GiB of 10.0 GiB (10.00%) in 10s",
                "TASK OK",
            ]
        ),
    )

    disk_move_watcher.main()

    output = capsys.readouterr().out.strip().splitlines()
    assert output[0].startswith("Monitoring disk move task: qmmove vmid=123 node=burns")
    assert output[-1] == "Final status: success"


def test_main_reports_no_task(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report no-task when nothing is being moved."""
    monkeypatch.setattr(
        disk_move_watcher, "read_active_tasks", lambda active_path=None: []
    )

    disk_move_watcher.main()

    assert capsys.readouterr().out.strip() == "Final status: no-task"


def test_main_lists_tasks_without_monitoring(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """List candidate tasks and exit without printing a final status."""
    monkeypatch.setattr(
        disk_move_watcher, "read_active_tasks", lambda active_path=None: [TASK]
    )

    disk_move_watcher.main(["--list"])

    output = capsys.readouterr().out
    assert TASK["upid"] in output
    assert "qmmove vmid=123 node=burns" in output
    assert "Final status" not in output


def test_main_reports_empty_listing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Say so plainly when the listing finds nothing."""
    monkeypatch.setattr(
        disk_move_watcher, "read_active_tasks", lambda active_path=None: []
    )

    disk_move_watcher.main(["--list"])

    assert capsys.readouterr().out.strip() == "No active disk move task found."


def test_main_honors_an_explicit_upid(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report no-task when the requested UPID is not among the active moves."""
    monkeypatch.setattr(
        disk_move_watcher, "read_active_tasks", lambda active_path=None: [TASK]
    )

    disk_move_watcher.main(["--upid", "UPID:burns:0:0:0:qmmove:999:root@pam:"])

    assert capsys.readouterr().out.strip() == "Final status: no-task"


def test_main_emits_debug_logs_on_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Emit debug lines on stderr when --debug is passed."""
    monkeypatch.setattr(
        disk_move_watcher, "read_active_tasks", lambda active_path=None: [TASK]
    )
    monkeypatch.setattr(
        disk_move_watcher,
        "resolve_disk_move_logfile",
        lambda task, tasks_root=None: Path("/tmp/fake-log"),
    )
    monkeypatch.setattr(
        disk_move_watcher,
        "monitor_disk_move_task",
        lambda *args, **kwargs: ([], "success"),
    )

    disk_move_watcher.main(["--debug"])

    assert "[debug]" in capsys.readouterr().err
