"""Tests for terminal width detection and per-frame output clipping."""

from __future__ import annotations

import collections

import watcher


def test_get_terminal_width_falls_back_to_eighty_outside_a_tty(monkeypatch) -> None:
    """Fall back to 80 columns when the terminal size cannot be determined."""

    def _not_a_terminal() -> None:
        raise OSError("not a terminal")

    monkeypatch.setattr(watcher.os, "get_terminal_size", _not_a_terminal)

    assert watcher.get_terminal_width() == 80


def test_get_terminal_width_rereads_the_size_on_every_call(monkeypatch) -> None:
    """Re-read the terminal size on each call instead of caching it once."""
    widths = iter([100, 60])
    monkeypatch.setattr(
        watcher.os,
        "get_terminal_size",
        lambda: collections.namedtuple("Size", "columns")(next(widths)),
    )

    assert watcher.get_terminal_width() == 100
    assert watcher.get_terminal_width() == 60


def test_get_plot_width_points_derives_from_a_given_terminal_width() -> None:
    """Derive the graph width from the terminal width, capped at 70."""
    assert watcher.get_plot_width_points(term_width_chars=100) == 70
    assert watcher.get_plot_width_points(term_width_chars=50) == 40


def test_get_plot_width_points_defaults_to_the_current_terminal_width(
    monkeypatch,
) -> None:
    """Fall back to get_terminal_width() when no width is passed in."""
    monkeypatch.setattr(watcher, "get_terminal_width", lambda: 90)

    assert watcher.get_plot_width_points() == 70


def test_clip_line_leaves_short_text_alone() -> None:
    """Return the text untouched when it already fits in the budget."""
    assert watcher.clip_line("abc", 10) == "abc"


def test_clip_line_cuts_to_the_requested_width() -> None:
    """Cut the line to exactly `width` characters when it overflows."""
    assert watcher.clip_line("abcdefgh", 3) == "abc"


def test_clip_line_ignores_a_non_positive_width() -> None:
    """Leave the line untouched when no usable width is known."""
    assert watcher.clip_line("abcdefgh", 0) == "abcdefgh"
    assert watcher.clip_line("abcdefgh", -1) == "abcdefgh"


def test_update_cli_display_never_writes_a_line_wider_than_the_terminal(
    monkeypatch, capsys
) -> None:
    """Clip every line of one rendered frame to the current terminal width.

    The in-place redraw counts screen rows via a fixed-height cursor-up
    escape, so a single line longer than the terminal would wrap and
    desynchronize every following frame. A very long status message is
    used here to force the header line past the width budget.
    """
    monkeypatch.setattr(watcher, "get_terminal_width", lambda: 40)
    watcher.first_cli_print_done = False

    task_details = {
        "vmid": "123",
        "upid": "UPID:burns:1:2:3:qmigrate:123:root@pam:",
    }
    speed_history = collections.deque([10.0, 20.0, 15.0], maxlen=70)
    recent_logs: collections.deque = collections.deque(maxlen=5)

    watcher.update_cli_display(
        task_details,
        times_list=[0, 91],
        progresses_list=[0.0, 5.5],
        total_gib_val=252.0,
        speed_history_q=speed_history,
        recent_logs_q=recent_logs,
        status_str="X" * 200,
    )

    captured = capsys.readouterr().out
    for raw_line in captured.split("\n"):
        visible = raw_line.replace("\033[2K", "")
        assert len(visible) <= 40
