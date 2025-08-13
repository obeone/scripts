from __future__ import annotations
"""
User Input and Event Handling Module.

This module is responsible for binding all user controls (keyboard shortcuts,
mouse events) to their corresponding actions within the application.
"""

import tkinter as tk
import logging
from tkinter import simpledialog, messagebox
from typing import TYPE_CHECKING

from . import hud

if TYPE_CHECKING:
    from .app import ImageSlideshowApp

logger = logging.getLogger(__name__)

def bind_controls(app: 'ImageSlideshowApp'):
    """
    Binds all keyboard shortcuts and mouse events to their handler functions.

    Args:
        app (ImageSlideshowApp): The main application instance.
    """
    # Playback and Navigation
    app.window.bind('<space>', lambda e: toggle_timer(app))
    app.window.bind('<Right>', lambda e: app.next_image())
    app.window.bind('<Left>', lambda e: app.previous_image())
    app.window.bind('<Up>', lambda e: app.jump_forward_ten())
    app.window.bind('<Down>', lambda e: app.jump_backward_ten())
    app.window.bind('<MouseWheel>', lambda e: on_scroll(app, e))
    app.window.bind('<Button-1>', lambda e: on_click(app, e))

    # Application Control
    app.window.bind('q', lambda e: app.quit())
    app.window.bind('Q', lambda e: app.quit())
    app.window.bind('<Escape>', lambda e: app.quit())

    # Image List Management
    app.window.bind('s', lambda e: app.shuffle_images())
    app.window.bind('t', lambda e: app.sort_images())
    app.window.bind('j', lambda e: jump_to_image(app))

    # Slideshow Parameters
    app.window.bind('=', lambda e: decrease_speed(app))
    app.window.bind('+', lambda e: decrease_speed(app))
    app.window.bind('-', lambda e: increase_speed(app))
    app.window.bind('b', lambda e: toggle_loop(app))
    app.window.bind('a', lambda e: toggle_auto_stop(app))

    # Display and Window Management
    app.window.bind('f', lambda e: toggle_fullscreen(app))
    app.window.bind('F', lambda e: toggle_fullscreen(app))
    app.window.bind('w', lambda e: toggle_always_on_top(app))
    app.window.bind('l', lambda e: increase_brightness(app))
    app.window.bind('k', lambda e: decrease_brightness(app))
    
    # Information and Favorites
    app.window.bind('i', lambda e: app.toggle_image_info())
    app.window.bind('z', lambda e: app.toggle_favorite())
    app.window.bind('h', lambda e: toggle_show_full_hud(app))
    
    # External Integration
    app.window.bind('y', lambda e: app.yoink_image())

    # Window Resize Event
    app.window.bind('<Configure>', app.on_resize)

def toggle_timer(app: 'ImageSlideshowApp'):
    app.toggle_timer()

def on_scroll(app: 'ImageSlideshowApp', event: tk.Event):
    if event.delta > 0 or event.num == 4:
        app.previous_image()
    elif event.delta < 0 or event.num == 5:
        app.next_image()

def on_click(app: 'ImageSlideshowApp', event: tk.Event):
    # Clicks on the HUD area should not toggle the timer
    # This is a simplified check; a more robust implementation
    # might involve checking widget identity.
    if event.y < app.canvas.winfo_height() - 100:
        toggle_timer(app)

def jump_to_image(app: 'ImageSlideshowApp'):
    if not app.images:
        messagebox.showinfo("Jump to Image", "No images loaded.", parent=app.window)
        return

    num_str = simpledialog.askstring(
        "Jump to Image",
        f"Enter image number (1 to {len(app.images)}):",
        parent=app.window
    )
    if num_str:
        try:
            index = int(num_str) - 1
            if 0 <= index < len(app.images):
                app.timer_running = False
                if app.after_id:
                    app.window.after_cancel(app.after_id)
                    app.after_id = None
                app.show_image(index)
            else:
                messagebox.showwarning("Invalid Input", f"Enter a number between 1 and {len(app.images)}.", parent=app.window)
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number.", parent=app.window)

def increase_speed(app: 'ImageSlideshowApp'):
    app.delay = max(0.1, app.delay - 0.5)
    logger.info(f"Slideshow delay decreased to {app.delay:.1f}s")
    hud.update_hud(app)

def decrease_speed(app: 'ImageSlideshowApp'):
    app.delay += 0.5
    logger.info(f"Slideshow delay increased to {app.delay:.1f}s")
    hud.update_hud(app)

def toggle_loop(app: 'ImageSlideshowApp'):
    app.loop = not app.loop
    logger.info(f"Slideshow loop {'enabled' if app.loop else 'disabled'}.")
    hud.update_hud(app)

def toggle_auto_stop(app: 'ImageSlideshowApp'):
    app.toggle_auto_stop()

def toggle_fullscreen(app: 'ImageSlideshowApp'):
    app.is_fullscreen = not app.is_fullscreen
    app.window.attributes('-fullscreen', app.is_fullscreen)
    logger.info(f"Fullscreen mode {'enabled' if app.is_fullscreen else 'disabled'}.")

def toggle_always_on_top(app: 'ImageSlideshowApp'):
    app.always_on_top = not app.always_on_top
    app.window.attributes('-topmost', app.always_on_top)
    logger.info(f"Always on top {'enabled' if app.always_on_top else 'disabled'}.")

def increase_brightness(app: 'ImageSlideshowApp'):
    app.brightness = min(3.0, app.brightness + 0.1)
    logger.info(f"Brightness increased to {app.brightness:.1f}")
    app.show_image(app.current_index, force_reload=True)

def decrease_brightness(app: 'ImageSlideshowApp'):
    app.brightness = max(0.1, app.brightness - 0.1)
    logger.info(f"Brightness decreased to {app.brightness:.1f}")
    app.show_image(app.current_index, force_reload=True)

def toggle_show_full_hud(app: 'ImageSlideshowApp'):
    app.show_full_hud = not app.show_full_hud
    logger.info(f"Full HUD display {'enabled' if app.show_full_hud else 'disabled'}.")
    hud.update_hud(app)
