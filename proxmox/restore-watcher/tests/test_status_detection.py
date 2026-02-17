"""Tests for terminal status detection and monitoring loop behavior."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Iterator

import restore_watcher


def test_detect_terminal_status_for_completion_lines() -> None:
    """Detect successful terminal status markers in task log lines."""
    lines = [
        "TASK OK",
        "restore completed in 2m 10s",
        "operation success",
    ]

    for line in lines:
        assert restore_watcher.detect_terminal_status(line) == "success"


def test_detect_terminal_status_for_failure_lines() -> None:
    """Detect failed terminal status markers in task log lines."""
    lines = [
        "TASK ERROR: restore failed",
        "restore failed with exit code 1",
        "restore aborted by user",
    ]

    for line in lines:
        assert restore_watcher.detect_terminal_status(line) == "failure"


def test_detect_terminal_status_for_neutral_line() -> None:
    """Return None for non-terminal task lines."""
    assert restore_watcher.detect_terminal_status("running backup extract step") is None


def test_collect_monitoring_data_stops_on_terminal_status() -> None:
    """Collect progress points and stop immediately on terminal status."""
    lines = [
        "transferred 1.0 GiB of 10.0 GiB (10.0%) in 10s",
        "transferred 2.0 GiB of 10.0 GiB (20.0%) in 20s",
        "TASK OK",
        "transferred 3.0 GiB of 10.0 GiB (30.0%) in 30s",
    ]

    points, terminal_status = restore_watcher.collect_monitoring_data(lines)

    assert terminal_status == "success"
    assert points == [(10, 1.0, 10.0), (20, 2.0, 10.0)]


def test_collect_monitoring_data_handles_keyboard_interrupt() -> None:
    """Return interrupted status when log following is interrupted."""

    def _interrupting_lines() -> Iterator[str]:
        yield "transferred 1.0 GiB of 10.0 GiB (10.0%) in 10s"
        raise KeyboardInterrupt

    points, terminal_status = restore_watcher.collect_monitoring_data(
        _interrupting_lines()
    )

    assert terminal_status == "interrupted"
    assert points == [(10, 1.0, 10.0)]


def test_choose_restore_task_auto_selects_when_only_one() -> None:
    """Automatically choose the single restore task without prompting."""
    task = {"upid": "UPID:node:1:2:A0000000:qmrestore:100:root@pam:"}

    selected = restore_watcher.choose_restore_task([task])

    assert selected == task


def test_main_prints_final_summary_line(tmp_path: Path, monkeypatch, capsys) -> None:
    """Always print one final summary line at the end of main."""
    task = {
        "upid": "UPID:node:1:2:A1234567:qmrestore:100:root@pam:",
        "action": "qmrestore",
        "status": "0",
        "raw": "UPID:node:1:2:A1234567:qmrestore:100:root@pam:",
    }
    logfile = tmp_path / "A" / task["upid"]
    logfile.parent.mkdir(parents=True)
    logfile.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        restore_watcher, "read_active_tasks", lambda active_path=None: [task]
    )
    monkeypatch.setattr(restore_watcher, "filter_restore_tasks", lambda tasks: tasks)
    monkeypatch.setattr(
        restore_watcher, "find_task_logfile", lambda upid_str, tasks_root=None: logfile
    )
    monkeypatch.setattr(
        restore_watcher,
        "follow_log_lines",
        lambda log_path: iter(
            [
                "transferred 1.0 GiB of 10.0 GiB (10.0%) in 10s",
                "TASK OK",
            ]
        ),
    )

    restore_watcher.main()

    output = capsys.readouterr().out.strip().splitlines()
    assert output[-1] == "Final status: success"


def test_collect_monitoring_data_prints_live_updates() -> None:
    """Print one live metrics update when progress points are parsed."""
    lines = [
        "transferred 1.0 GiB of 10.0 GiB (10.0%) in 10s",
        "transferred 2.0 GiB of 10.0 GiB (20.0%) in 20s",
        "TASK OK",
    ]
    output_stream = StringIO()

    points, status = restore_watcher.collect_monitoring_data(
        lines,
        output_stream=output_stream,
        update_interval_seconds=60.0,
        now_fn=lambda: 0.0,
    )

    output_lines = output_stream.getvalue().strip().splitlines()
    assert status == "success"
    assert points[-1] == (20, 2.0, 10.0)
    assert any(line.startswith("[") for line in output_lines)
    assert any("MiB/s" in line for line in output_lines)


def test_collect_monitoring_data_prints_heartbeat_without_progress() -> None:
    """Print a heartbeat when no progress line is parsed for too long."""
    lines = [
        "restoring archive",
        "TASK OK",
    ]
    output_stream = StringIO()
    clock_values = iter([0.0, 2.0, 2.0])

    points, status = restore_watcher.collect_monitoring_data(
        lines,
        output_stream=output_stream,
        update_interval_seconds=1.0,
        now_fn=lambda: next(clock_values),
    )

    output_text = output_stream.getvalue()
    assert points == []
    assert status == "success"
    assert "waiting log" in output_text


def test_debug_mode_logs_to_stderr(monkeypatch, capsys) -> None:
    """Emit debug logs on stderr when --debug is enabled."""
    task = {
        "upid": "UPID:node:1:2:A1234567:qmrestore:100:root@pam:",
        "action": "qmrestore",
        "status": "0",
        "raw": "UPID:node:1:2:A1234567:qmrestore:100:root@pam:",
    }

    monkeypatch.setattr(
        restore_watcher, "read_active_tasks", lambda active_path=None: [task]
    )
    monkeypatch.setattr(restore_watcher, "filter_restore_tasks", lambda tasks: tasks)
    monkeypatch.setattr(
        restore_watcher,
        "resolve_restore_logfile",
        lambda current_task, tasks_root=None: Path("/tmp/fake-log"),
    )
    monkeypatch.setattr(
        restore_watcher,
        "monitor_restore_task",
        lambda *args, **kwargs: ([], "success"),
    )

    restore_watcher.main(["--debug"])

    captured = capsys.readouterr()
    assert "[debug]" in captured.err


def test_build_dashboard_lines_keeps_only_five_recent_logs() -> None:
    """Render only the five most recent log lines under status line."""
    points = [(10, 1.0, 10.0), (20, 2.0, 10.0)]
    logs = [f"log-{index}" for index in range(8)]

    lines = restore_watcher.build_dashboard_lines(
        points,
        speed_gib_s=0.1,
        eta_seconds=80.0,
        recent_logs=logs,
        waiting=False,
        color=False,
    )

    assert len(lines) == 6
    assert lines[1].endswith("log-3")
    assert lines[-1].endswith("log-7")
