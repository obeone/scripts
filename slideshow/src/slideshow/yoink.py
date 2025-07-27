"""
macOS Yoink Integration Utility.

This module provides a utility function to send a file to the Yoink application,
a shelf app for macOS that makes drag-and-drop easier. The functionality is
platform-specific and will only execute on macOS.
"""

import sys
import subprocess
import logging
from pathlib import Path
import tkinter as tk

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def send_to_yoink(image_path: Path, canvas: tk.Canvas | None = None) -> None:
    """
    Sends the specified image file to the Yoink application on macOS.

    If the operating system is not macOS, it logs a warning and can optionally
    display a temporary message on a Tkinter canvas if one is provided.

    Args:
        image_path (Path): The absolute path to the image file to be sent.
        canvas (tk.Canvas | None): An optional Tkinter Canvas widget to display
                                  a message on non-macOS platforms. Defaults to None.
    """
    if sys.platform == "darwin":  # 'darwin' is the platform name for macOS
        try:
            command = ["open", "-a", "Yoink", str(image_path)]
            # `check=False` prevents raising an error if Yoink isn't found.
            subprocess.run(command, check=False, capture_output=True, text=True)
            logger.info(f"Attempted to send image to Yoink: {image_path.name}")
        except FileNotFoundError:  # Should not happen for 'open' on macOS
            logger.error("Yoink: The 'open' command was not found. This is unexpected on macOS.")
        except Exception as e:
            logger.error(f"Yoink: Failed to send '{image_path.name}': {e}")
    else:
        logger.warning("Yoink functionality is only available on macOS.")
        # Display a temporary message on the canvas if provided
        if canvas and canvas.winfo_exists():
            canvas.delete("yoink_message")  # Clear previous message
            if canvas.winfo_width() > 1 and canvas.winfo_height() > 1:
                canvas.create_text(
                    canvas.winfo_width() / 2, canvas.winfo_height() / 2,
                    text="Yoink is a macOS only feature", fill="yellow",
                    font=("Helvetica", 16, "bold"), tags="yoink_message", anchor=tk.CENTER
                )
                # Schedule the message to disappear after 2.5 seconds
                canvas.after(2500, lambda: canvas.delete("yoink_message"))
