"""Tests for terminal migration status detection."""

from __future__ import annotations

import watcher


def test_detect_terminal_status_recognizes_task_ok() -> None:
    """Recognize a plain TASK OK line as a successful terminal status."""
    assert watcher.detect_terminal_status("TASK OK") == "ok"


def test_detect_terminal_status_recognizes_qmigrate_success_markers() -> None:
    """Recognize the qmigrate-specific completion markers as success."""
    assert watcher.detect_terminal_status("migration status: completed") == "ok"
    assert watcher.detect_terminal_status("migration finished successfully") == "ok"


def test_detect_terminal_status_treats_task_warnings_as_terminal() -> None:
    """Treat TASK WARNINGS as terminal, since TASK OK never follows it."""
    assert watcher.detect_terminal_status("TASK WARNINGS: 1") == "warnings"


def test_detect_terminal_status_recognizes_failure_markers() -> None:
    """Recognize every qmigrate failure marker as a terminal error."""
    assert watcher.detect_terminal_status("TASK ERROR: something broke") == "error"
    assert watcher.detect_terminal_status("migration status: failed") == "error"
    assert watcher.detect_terminal_status("migration aborted") == "error"


def test_detect_terminal_status_returns_none_for_a_progress_line() -> None:
    """Return None for an ordinary progress line, which is not terminal."""
    line = "drive-scsi0: transferred 5.5 GiB of 252.0 GiB (2.18%) in 1m 31s"

    assert watcher.detect_terminal_status(line) is None


def test_detect_terminal_status_returns_none_for_an_unrelated_line() -> None:
    """Return None for a line with no terminal marker of any kind."""
    assert watcher.detect_terminal_status("all 'mirror' jobs are ready") is None
