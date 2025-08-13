from __future__ import annotations
"""
Heads-Up Display (HUD) Module.

This module is responsible for rendering the on-screen display that shows
slideshow status, image information, and keyboard shortcuts.
"""

import tkinter as tk
import logging
import time
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .app import ImageSlideshowApp

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def get_hud_shortcut_text() -> str:
    """
    Generates the detailed help text string containing keyboard shortcuts.

    Returns:
        str: A formatted string listing the available keyboard shortcuts.
    """
    shortcuts = [
        "Shortcuts (h to toggle):",
        "  Play/Pause: Space | Next/Prev: →/←, Scroll | Jump +/-10: ↑/↓",
        "  Speed +/-: -/= | Brightness +/-: k/l | Fullscreen: f | Always on Top: w",
        "  Shuffle: s | Sort by Time: t | Jump to #: j | Loop: b | Auto-Stop: a",
        "  Info: i | Favorite: z | Yoink (macOS): y | Quit: q, Esc"
    ]
    return "\n".join(shortcuts)

def update_hud(app: 'ImageSlideshowApp') -> None:
    """
    Updates and redraws the Heads-Up Display (HUD) on the canvas.

    The HUD shows slideshow status (play/pause, image count, delay, etc.)
    and optionally a list of keyboard shortcuts.

    Args:
        app (ImageSlideshowApp): The main application instance, used to access
                                 the current state (e.g., timer_running, delay)
                                 and the canvas to draw on.
    """
    # Clear previous HUD elements to prevent overlap
    app.canvas.delete("hud_bg", "hud_text")

    canvas_width = app.canvas.winfo_width()
    canvas_height = app.canvas.winfo_height()

    # Define minimum canvas dimensions for the HUD to be practical
    MIN_CANVAS_WIDTH_FOR_HUD = 200
    MIN_CANVAS_HEIGHT_FOR_HUD = 60
    if canvas_width < MIN_CANVAS_WIDTH_FOR_HUD or canvas_height < MIN_CANVAS_HEIGHT_FOR_HUD:
        logger.debug(f"Canvas too small ({canvas_width}x{canvas_height}) to draw HUD.")
        return

    # --- Gather HUD information strings ---
    play_status = "Playing" if app.timer_running else "Paused"
    loop_status = "Loop: On" if app.loop else "Loop: Off"
    auto_stop_status = "AutoStop: On" if app.auto_stop else "AutoStop: Off"
    if app.auto_stop and app.stop_time > 0:
        time_remaining = max(0, int(app.stop_time - time.time()))
        auto_stop_status += f" ({time_remaining}s)"

    image_count_str = "No images"
    current_image_name = ""
    if app.images and 0 <= app.current_index < len(app.images):
        image_path = app.images[app.current_index]
        image_count_str = f"{app.current_index + 1}/{len(app.images)}"
        if app.current_index in app.favorites:
            image_count_str += " ★"  # Star symbol for favorited image
        
        current_image_name = image_path.name
        MAX_NAME_LEN_HUD = 40
        if len(current_image_name) > MAX_NAME_LEN_HUD:
            current_image_name = current_image_name[:MAX_NAME_LEN_HUD-3] + "..."
    
    delay_str = f"Delay: {app.delay:.1f}s"
    brightness_str = f"Bright: {app.brightness:.1f}"

    # Assemble HUD lines
    hud_lines = [
        f"{play_status} | {image_count_str}{' - ' + current_image_name if current_image_name else ''}",
        f"{delay_str} | {brightness_str} | {loop_status} | {auto_stop_status}",
    ]

    if app.show_full_hud:
        shortcut_text = get_hud_shortcut_text()
        if shortcut_text:
            hud_lines.append(shortcut_text)

    final_hud_text = "\n".join(filter(None, hud_lines))

    if not final_hud_text.strip():
        logger.debug("HUD text is empty, skipping drawing.")
        return

    # --- Drawing parameters ---
    padding = 8
    font_size = 10
    hud_font = ("Helvetica", font_size, "bold")

    # Use a temporary text object to measure the required bounding box
    temp_text_item = app.canvas.create_text(0, 0, text=final_hud_text, font=hud_font, anchor='sw', tags="temp")
    x1, y1, x2, y2 = app.canvas.bbox(temp_text_item)
    app.canvas.delete(temp_text_item)
    
    text_width = x2 - x1
    text_height = y2 - y1

    # Position the background rectangle at the bottom-center of the canvas
    rect_x1 = (canvas_width - text_width) / 2 - padding
    rect_y1 = canvas_height - text_height - (2 * padding)
    rect_x2 = (canvas_width + text_width) / 2 + padding
    rect_y2 = canvas_height

    # Draw the semi-transparent background rectangle
    app.canvas.create_rectangle(
        rect_x1, rect_y1, rect_x2, rect_y2,
        fill="black", outline="", stipple="gray50", tags="hud_bg"
    )

    # Draw the HUD text on top of the background
    app.canvas.create_text(
        rect_x1 + padding,
        rect_y2 - padding,
        text=final_hud_text,
        anchor='sw',
        fill="white",
        font=hud_font,
        tags="hud_text"
    )
