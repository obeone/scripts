"""
Extra tests for the controls module to improve coverage.

This module tests the following high-priority cases:
- Callbacks for HUD updates
- Scroll events
- Speed and brightness adjustments
- Loop toggling
"""

import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

from slideshow import controls

# Mock the main app instance for testing controls
@pytest.fixture
def mock_app():
    """Fixture to create a mock application instance for testing controls."""
    app = MagicMock()
    app.window = MagicMock()
    app.canvas = MagicMock()
    app.images = ["image1.jpg", "image2.jpg"]
    app.current_index = 0
    app.delay = 5.0
    app.loop = False
    app.brightness = 1.0
    app.show_full_hud = False
    app.after_id = None
    app.timer_running = False
    return app

# Mock the event instance for testing scroll and click events
@pytest.fixture
def mock_event():
    """Fixture to create a mock event instance."""
    event = MagicMock(spec=tk.Event)
    event.delta = 0
    event.num = 0
    return event

# Test cases for on_scroll function
@pytest.mark.parametrize(
    "delta, num, expected_call",
    [
        (120, 0, "previous_image"),  # Scroll up (Windows/macOS)
        (-120, 0, "next_image"),    # Scroll down (Windows/macOS)
        (0, 4, "previous_image"),    # Scroll up (Linux)
        (0, 5, "next_image"),      # Scroll down (Linux)
    ],
)
def test_on_scroll(mock_app, mock_event, delta, num, expected_call):
    """
    Test that on_scroll calls the correct image navigation method.
    """
    mock_event.delta = delta
    mock_event.num = num
    
    controls.on_scroll(mock_app, mock_event)
    
    if expected_call == "previous_image":
        mock_app.previous_image.assert_called_once()
        mock_app.next_image.assert_not_called()
    elif expected_call == "next_image":
        mock_app.next_image.assert_called_once()
        mock_app.previous_image.assert_not_called()

# Test cases for speed control functions
def test_increase_speed(mock_app):
    """
    Test that increase_speed decreases the delay correctly.
    """
    initial_delay = mock_app.delay
    with patch("slideshow.controls.hud.update_hud") as mock_update_hud:
        controls.increase_speed(mock_app)
        assert mock_app.delay == initial_delay - 0.5
        mock_update_hud.assert_called_once_with(mock_app)

def test_decrease_speed(mock_app):
    """
    Test that decrease_speed increases the delay correctly.
    """
    initial_delay = mock_app.delay
    with patch("slideshow.controls.hud.update_hud") as mock_update_hud:
        controls.decrease_speed(mock_app)
        assert mock_app.delay == initial_delay + 0.5
        mock_update_hud.assert_called_once_with(mock_app)

def test_increase_speed_at_minimum_delay(mock_app):
    """
    Test that increase_speed does not go below the minimum delay.
    """
    mock_app.delay = 0.5
    with patch("slideshow.controls.hud.update_hud"):
        controls.increase_speed(mock_app)
        assert mock_app.delay == 0.1

# Test case for toggle_loop function
def test_toggle_loop(mock_app):
    """
    Test that toggle_loop inverts the loop attribute.
    """
    initial_loop = mock_app.loop
    with patch("slideshow.controls.hud.update_hud") as mock_update_hud:
        controls.toggle_loop(mock_app)
        assert mock_app.loop is not initial_loop
        mock_update_hud.assert_called_once_with(mock_app)

# Test cases for brightness control functions
def test_increase_brightness(mock_app):
    """
    Test that increase_brightness increases the brightness and reloads the image.
    """
    initial_brightness = mock_app.brightness
    controls.increase_brightness(mock_app)
    assert mock_app.brightness == pytest.approx(initial_brightness + 0.1)
    mock_app.show_image.assert_called_once_with(mock_app.current_index, force_reload=True)

def test_decrease_brightness(mock_app):
    """
    Test that decrease_brightness decreases the brightness and reloads the image.
    """
    initial_brightness = mock_app.brightness
    controls.decrease_brightness(mock_app)
    assert mock_app.brightness == pytest.approx(initial_brightness - 0.1)
    mock_app.show_image.assert_called_once_with(mock_app.current_index, force_reload=True)

def test_increase_brightness_at_max(mock_app):
    """
    Test that increase_brightness does not exceed the maximum brightness.
    """
    mock_app.brightness = 3.0
    controls.increase_brightness(mock_app)
    assert mock_app.brightness == 3.0

def test_decrease_brightness_at_min(mock_app):
    """
    Test that decrease_brightness does not go below the minimum brightness.
    """
    mock_app.brightness = 0.1
    controls.decrease_brightness(mock_app)
    assert mock_app.brightness == pytest.approx(0.1)

# Test case for toggle_show_full_hud function
def test_toggle_show_full_hud(mock_app):
    """
    Test that toggle_show_full_hud inverts the show_full_hud attribute.
    """
    initial_show_full_hud = mock_app.show_full_hud
    with patch("slideshow.controls.hud.update_hud") as mock_update_hud:
        controls.toggle_show_full_hud(mock_app)
        assert mock_app.show_full_hud is not initial_show_full_hud
        mock_update_hud.assert_called_once_with(mock_app)
