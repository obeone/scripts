"""
Command-Line Interface for the Image Slideshow application.

This module handles parsing of command-line arguments, sets up logging,
and initializes and runs the main application.
"""

import argparse
import tkinter as tk
import logging
import coloredlogs
import sys
import importlib.metadata
from pathlib import Path

from .app import ImageSlideshowApp
from . import config

# Setup a dedicated logger for this application
logger = logging.getLogger(__name__)

def main():
    """
    The main entry point for the application.
    
    Parses command-line arguments, sets up the application window and logging,
    and starts the slideshow.
    """
    parser = argparse.ArgumentParser(
        description="A feature-rich image slideshow viewer.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {importlib.metadata.version('slideshow')}",
        help="Show the version number and exit."
    )
    parser.add_argument(
        "image_folder",
        type=str,
        help="The folder containing images to display."
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=config.DEFAULT_DELAY,
        help=f"Delay in seconds between images. Default: {config.DEFAULT_DELAY}"
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle the image order."
    )
    parser.add_argument(
        "--sort-desc",
        action="store_true",
        help="Sort images by modification time (newest first)."
    )
    parser.add_argument(
        "--auto-stop",
        type=int,
        nargs='?',
        const=config.DEFAULT_AUTO_STOP_DELAY,
        default=None,
        metavar='SECONDS',
        help=f"Stop the slideshow automatically after a set time.\n"
             f"If no time is given, defaults to {config.DEFAULT_AUTO_STOP_DELAY} seconds."
    )
    parser.add_argument(
        "-l", "--log-level",
        type=str,
        default=config.DEFAULT_LOG_LEVEL,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help=f"Set the logging level. Default: {config.DEFAULT_LOG_LEVEL}"
    )
    args = parser.parse_args()

    # --- Setup Logging ---
    log_level_upper = args.log_level.upper()
    # Configure root logger
    logging.basicConfig(level=getattr(logging, log_level_upper, logging.INFO))
    # Install coloredlogs for our specific logger instance
    coloredlogs.install(
        level=log_level_upper,
        logger=logger,
        fmt='%(asctime)s %(levelname)-8s %(name)s: %(message)s'
    )
    # Set level for other loggers if they become too verbose
    logging.getLogger().setLevel(getattr(logging, log_level_upper, logging.INFO))

    # --- Application Initialization ---
    try:
        root = tk.Tk()
        # Hide the main window initially until the app decides to show it
        root.withdraw() 
        
        app = ImageSlideshowApp(
            window=root,
            image_folder=args.image_folder,
            delay=args.delay,
            auto_stop_delay=args.auto_stop
        )

        # Post-initialization setup based on CLI args
        if app.images: # Only if images were loaded successfully
            if args.shuffle:
                app.shuffle_images()
            elif args.sort_desc:
                # Default sort is ascending, so we only need to act on desc
                app.images = sorted(app.images, key=lambda p: p.stat().st_mtime, reverse=True)
                app.current_index = 0
                app.show_image(0)

            # Un-hide the window now that the app is ready
            root.deiconify()
            app.run()
        else:
            # If app initialization failed (e.g., no images), exit gracefully.
            # The app itself handles showing an error message.
            logger.critical("Application startup failed, likely no images found.")
            sys.exit(1)

    except FileNotFoundError:
        logger.error(f"The specified image folder does not exist: {args.image_folder}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
