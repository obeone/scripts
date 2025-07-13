#!/usr/bin/env python3

import tkinter as tk
from tkinter import simpledialog, messagebox
import logging
import coloredlogs # For colored console output
# import os  # Removed unused import to clean up code
import argparse
import random
import sys
import time
from pathlib import Path # For modern path manipulation
from PIL import Image, ImageTk, ImageEnhance, ImageSequence # Pillow for image manipulation
from PIL.ExifTags import TAGS # To get human-readable EXIF tags
import subprocess # For running external commands like 'Yoink'

# Setup a dedicated logger for this application
logger = logging.getLogger(__name__)

class ImageSlideshowApp:
    '''
    A feature-rich Tkinter application for displaying a slideshow of images.

    This application allows users to view images from a specified folder in a
    fullscreen slideshow. It offers various functionalities including automatic
    playback with adjustable delay, manual navigation, image shuffling and sorting,
    brightness adjustment, favoriting images, displaying image information (including EXIF data),
    and integration with macOS Yoink for quick image sharing/saving.

    Attributes:
        window (tk.Tk): The main Tkinter window instance.
        image_folder (Path): The Path object pointing to the directory containing images.
        delay (float): Time in seconds between image transitions during automatic playback.
        timer_running (bool): Flag indicating if the automatic slideshow timer is active.
        loop (bool): Flag indicating if the slideshow should loop back to the beginning after the last image.
        auto_stop (bool): Flag indicating if the slideshow should stop automatically after a predefined duration.
        stop_time (float): Timestamp (seconds since epoch) when auto_stop should trigger.
        auto_stop_delay (int): Duration in seconds for the auto_stop feature.
        current_index (int): Index of the currently displayed image in the `images` list.
        after_id (str | None): ID of the scheduled `after` event for slideshow advancement.
        info_displayed (bool): Flag indicating if the image information overlay is visible.
        is_fullscreen (bool): Flag indicating if the application is in fullscreen mode.
        always_on_top (bool): Flag indicating if the application window should stay above others.
        sort_ascending (bool): Determines sort order for images (True for ascending by ctime).
        brightness (float): Current brightness enhancement factor for images (1.0 is original).
        images (list[Path]): List of Path objects for all valid images found.
        icons (dict[str, ImageTk.PhotoImage]): Dictionary to store loaded UI icons (currently placeholder).
        preloaded_images (dict[int, Image.Image]): Cache for preloaded PIL Image objects.
        favorites (list[int]): List of indices of images marked as favorite.
        show_full_hud (bool): Flag to control the visibility of the detailed help text in the HUD.
        canvas (tk.Canvas): The Tkinter Canvas widget used for displaying images and overlays.
        _resize_job (str | None): Stores the ID of an 'after' job for debouncing resize events.
        _gif_animation_after_id (str | None): Stores the ID of an 'after' job for GIF frame animation.
        _animate_gif_frames (list[ImageTk.PhotoImage]): Stores PhotoImage objects for current GIF frames.
        _animate_gif_durations (list[int]): Stores duration for each frame of the current GIF.
        _animate_gif_idx (int): Current frame index for GIF animation.
    '''

    def __init__(self, window: tk.Tk, image_folder: str, delay: float = 3.0, auto_stop_delay: int | None = None, preload_count: int = 20, log_level: str = 'WARNING'):
        '''
        Initializes the ImageSlideshowApp instance, sets up UI and loads images.

        Args:
            window (tk.Tk): The main Tkinter window.
            image_folder (str): Path to the folder containing images.
            delay (float): Delay between images in seconds for automatic slideshow. Defaults to 3.0.
            auto_stop_delay (int | None): Delay in seconds after which the slideshow automatically stops.
                                         If None, auto-stop is initially off. Defaults to None.
            log_level (str): Logging level (e.g., 'DEBUG', 'INFO', 'WARNING'). Defaults to 'WARNING'.
        '''
        log_level_upper = log_level.upper()
        # Configure root logger if no handlers are present (e.g., first time)
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(level=getattr(logging, log_level_upper, logging.INFO))
        
        # Install coloredlogs for our specific logger instance
        coloredlogs.install(level=log_level_upper, logger=logger, fmt='%(asctime)s %(levelname)-8s %(name)s: %(message)s')
        # Optionally, set the level for other loggers (e.g., Pillow) if they become too verbose
        logging.getLogger().setLevel(getattr(logging, log_level_upper, logging.INFO)) # Affects root logger

        self.window = window
        self.image_folder = Path(image_folder).resolve() # Resolve to absolute path
        self.delay = float(delay)
        self.timer_running = True
        self.loop = True
        self.auto_stop = False # Auto-stop is off by default, enabled by CLI arg or key press
        self.stop_time = 0.0
        self.auto_stop_delay = auto_stop_delay if auto_stop_delay is not None else 3600 # Default 1 hour if enabled
        
        self.current_index = 0
        self.after_id: str | None = None
        self.info_displayed = False
        self.is_fullscreen = True
        self.always_on_top = False
        self.sort_ascending = True # True for 'oldest first' when sorting by ctime
        self.brightness = 1.0
        
        self.images: list[Path] = []
        self.icons: dict[str, ImageTk.PhotoImage] = {} # For potential future use
        self.preloaded_images: dict[int, Image.Image] = {}
        self.favorites: list[int] = []
        
        self.show_full_hud = True # Show detailed help in HUD by default
        self._resize_job: str | None = None # For debouncing resize events
        self._gif_animation_after_id: str | None = None # For managing GIF frame updates

        # Initialize attributes for GIF animation state
        self._animate_gif_frames: list[ImageTk.PhotoImage] = []
        self._animate_gif_durations: list[int] = []
        self._animate_gif_idx: int = 0

        self.preload_count = preload_count  # Number of images to preload by default

        self.load_icons() # Load any UI icons (currently placeholder)
        self.load_images() # Discover and list all image files
        self.load_favorites() # Load previously favorited image indices

        if not self.images:
            logger.error("No valid images found in the specified folder. Application will close.")
            messagebox.showerror("Error", "No valid images found in the specified folder.\nPlease check the folder and image formats.", parent=self.window)
            # Schedule destroy because direct destroy in __init__ can be problematic
            self.window.after(50, self.window.destroy) 
            return

        self.window.title("Image Slideshow")
        self.window.attributes('-fullscreen', self.is_fullscreen)
        self.window.configure(bg='black') # Black background for the window
        
        self.bind_keys() # Setup keyboard and mouse bindings
        self.window.bind('<Configure>', self.on_resize) # Handle window resize events

        self.canvas = tk.Canvas(self.window, bg='black', highlightthickness=0) # Main display area
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Initial image display is typically handled by the __main__ block after CLI arg processing
        # or can be called here if no further setup is needed.
        # self.show_image(self.current_index)

    def bind_keys(self) -> None:
        '''
        Binds keyboard shortcuts and mouse events to their respective handler functions.
        '''
        # Playback and Navigation
        self.window.bind('<space>', self.toggle_timer)
        self.window.bind('<Right>', self.next_image)
        self.window.bind('<Left>', self.previous_image)
        self.window.bind('<MouseWheel>', self.on_scroll) # Scroll for next/prev
        self.window.bind('<Button-1>', self.on_click)    # Left-click to toggle play/pause

        # Application Control
        self.window.bind('q', self.quit)
        self.window.bind('Q', self.quit) # Allow shifted Q
        self.window.bind('<Escape>', self.quit)

        # Image List Management
        self.window.bind('s', self.shuffle_images)
        self.window.bind('t', self.sort_images) # Sort by creation time
        self.window.bind('j', self.jump_to_image) # Jump to a specific image index

        # Slideshow Parameters
        self.window.bind('=', self.decrease_speed) # '+' key usually needs Shift
        self.window.bind('+', self.decrease_speed) # Slower slideshow (increases delay)
        self.window.bind('-', self.increase_speed) # Faster slideshow (decreases delay)
        self.window.bind('b', self.toggle_loop)    # Toggle looping
        self.window.bind('a', self.toggle_auto_stop) # Toggle auto-stop feature

        # Display and Window Management
        self.window.bind('f', self.toggle_fullscreen)
        self.window.bind('F', self.toggle_fullscreen) # Allow shifted F
        self.window.bind('w', self.toggle_always_on_top)
        self.window.bind('l', self.increase_brightness) # 'l' for Lighter
        self.window.bind('k', self.decrease_brightness) # 'k' for darKer (mnemonic)
        
        # Information and Favorites
        self.window.bind('i', self.toggle_image_info) # Toggle image metadata display
        self.window.bind('z', self.toggle_favorite)   # Toggle image favorite status
        self.window.bind('h', self.toggle_show_full_hud) # Toggle detailed HUD help
        
        # External Integration
        self.window.bind('y', self.yoink_image) # Send to Yoink (macOS)

    def toggle_show_full_hud(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the visibility of the detailed help text (shortcuts) in the HUD.

        Args:
            event (tk.Event | None): The Tkinter event that triggered this callback. Defaults to None.
        '''
        self.show_full_hud = not self.show_full_hud
        logger.info(f"Full HUD (shortcuts) display: {'Enabled' if self.show_full_hud else 'Disabled'}")
        self.update_hud() # Refresh HUD to reflect the change

    def yoink_image(self, event: tk.Event | None = None) -> None:
        '''
        Sends the current image's path to the Yoink application on macOS.
        Yoink is a utility that provides a temporary shelf for files.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images or not (0 <= self.current_index < len(self.images)):
            logger.warning("Yoink: No image currently selected or image list is empty.")
            return

        image_path = self.images[self.current_index]
        if sys.platform == "darwin": # 'darwin' is the platform name for macOS
            try:
                command = ["open", "-a", "Yoink", str(image_path)]
                # `check=False` means it won't raise an error if Yoink isn't found or returns non-zero.
                subprocess.run(command, check=False, capture_output=True, text=True)
                logger.info(f"Attempted to send image to Yoink: {image_path.name}")
            except FileNotFoundError: # Should not happen for 'open' on macOS
                logger.error("Yoink: The 'open' command was not found. This is unexpected on macOS.")
            except Exception as e:
                logger.error(f"Yoink: Failed to send '{image_path.name}': {e}")
        else:
            logger.warning("Yoink functionality is only available on macOS.")
            # Display a temporary message on the canvas
            self.canvas.delete("yoink_message") # Clear previous message
            # Ensure canvas is ready before drawing text
            if self.canvas.winfo_width() > 1 and self.canvas.winfo_height() > 1:
                self.canvas.create_text(
                    self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2,
                    text="Yoink is a macOS only feature", fill="yellow",
                    font=("Helvetica", 16, "bold"), tags="yoink_message", anchor=tk.CENTER
                )
                self.window.after(2500, lambda: self.canvas.delete("yoink_message"))

    def toggle_favorite(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the favorite status of the currently displayed image.
        Favorites are stored by their index in the `images` list.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images or not (0 <= self.current_index < len(self.images)):
            logger.warning("Favorite toggle: No image selected or image list empty.")
            return
        
        image_name = self.images[self.current_index].name
        if self.current_index in self.favorites:
            self.favorites.remove(self.current_index)
            logger.info(f"Image {self.current_index + 1} ('{image_name}') removed from favorites.")
        else:
            self.favorites.append(self.current_index)
            logger.info(f"Image {self.current_index + 1} ('{image_name}') added to favorites.")
        self.favorites.sort() # Keep the list of favorite indices sorted
        self.update_hud() # Update HUD to reflect favorite status change

    def load_favorites(self) -> None:
        '''
        Loads favorite image indices from a 'favorites.txt' file located in the image folder.
        Filters indices to ensure they are valid for the currently loaded image list.
        '''
        favorites_file = self.image_folder / 'favorites.txt'
        if favorites_file.exists() and self.images: # Only load if file exists and images are present
            try:
                with open(favorites_file, 'r', encoding='utf-8') as f:
                    # Read indices, ensuring they are digits and stripping whitespace
                    loaded_indices = [int(line.strip()) for line in f if line.strip().isdigit()]
                    # Filter to keep only valid indices within the current image list bounds
                    self.favorites = [idx for idx in loaded_indices if 0 <= idx < len(self.images)]
                logger.info(f"Loaded {len(self.favorites)} valid favorite indices from {favorites_file}.")
            except ValueError:
                logger.error(f"Error parsing favorite indices from '{favorites_file}'. File might be corrupt.")
            except Exception as e:
                logger.error(f"Error loading favorites from '{favorites_file}': {e}")
        elif not self.images:
            logger.info("Favorites not loaded: Image list is currently empty.")
        else:
            logger.debug(f"Favorites file not found: {favorites_file}. No favorites to load.")

    def save_favorites(self) -> None:
        '''
        Saves the current list of favorite image indices to 'favorites.txt' in the image folder.
        Only valid indices are saved.
        '''
        if not self.image_folder.exists():
            try: # Attempt to create the folder if it's missing (e.g., for a new set of images)
                self.image_folder.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created image folder at {self.image_folder} for saving favorites.")
            except OSError as e:
                logger.error(f"Cannot save favorites: Image folder '{self.image_folder}' does not exist and could not be created. Error: {e}")
                return
        
        favorites_file = self.image_folder / 'favorites.txt'
        try:
            # Filter out invalid indices before saving (e.g., if image list changed)
            valid_favorites = [idx for idx in self.favorites if 0 <= idx < len(self.images)]
            with open(favorites_file, 'w', encoding='utf-8') as f:
                for index in sorted(list(set(valid_favorites))): # Ensure uniqueness and sort
                    f.write(f"{index}\n")
            logger.info(f"Saved {len(valid_favorites)} favorite indices to {favorites_file}.")
        except Exception as e:
            logger.error(f"Error saving favorites to '{favorites_file}': {e}")

    def jump_to_image(self, event: tk.Event | None = None) -> None:
        '''
        Prompts the user to enter an image number (1-based) and jumps to that image.
        Pauses the slideshow timer upon jumping.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images:
            messagebox.showinfo("Jump to Image", "No images loaded to jump to.", parent=self.window)
            return

        # AskString allows more flexible input, then convert to int
        image_index_str = simpledialog.askstring(
            "Jump to Image",
            f"Enter image number (1 to {len(self.images)}):",
            parent=self.window # Ensure dialog is modal to the main window
        )

        if image_index_str: # If user provided input (didn't cancel)
            try:
                image_index_one_based = int(image_index_str)
                if 1 <= image_index_one_based <= len(self.images):
                    self.timer_running = False # Pause timer on manual jump
                    if self.after_id: # Cancel any pending auto-advance
                        self.window.after_cancel(self.after_id)
                        self.after_id = None
                    self.show_image(image_index_one_based - 1) # Convert 1-based to 0-based index
                else:
                    msg = f"Invalid image number. Please enter a number between 1 and {len(self.images)}."
                    logger.warning(msg)
                    messagebox.showwarning("Invalid Input", msg, parent=self.window)
            except ValueError:
                msg = "Invalid input. Please enter a valid image number."
                logger.error(f"{msg} User entered: '{image_index_str}'")
                messagebox.showerror("Invalid Input", msg, parent=self.window)

    def load_icons(self) -> None:
        '''
        Loads UI icons from the 'slideshow-img' subdirectory relative to the script.
        This method is a placeholder for future use if icons are displayed in the UI.
        '''
        try:
            # Resolve path relative to the script file
            base_path = Path(__file__).resolve().parent
        except NameError: # __file__ might not be defined (e.g., in interactive interpreter)
            base_path = Path.cwd().resolve()
        
        ICONS_PATH = base_path / 'slideshow-img'
        logger.debug(f"Looking for icons in: {ICONS_PATH}")

        # Example: if self.icons dictionary were to be used later
        # icon_files_map = {"play_icon": "play.png", "pause_icon": "pause.png"}
        # for icon_name, filename in icon_files_map.items():
        #     icon_path = ICONS_PATH / filename
        #     try:
        #         if icon_path.is_file():
        #             pil_image = Image.open(icon_path)
        #             pil_image.load() # Ensure image data is loaded
        #             # Resize for consistency if icons are displayed
        #             # resized_icon = pil_image.resize((24, 24), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)
        #             # self.icons[icon_name] = ImageTk.PhotoImage(resized_icon)
        #         else:
        #             logger.warning(f"Icon file not found: {icon_path}")
        #     except Exception as e:
        #         logger.error(f"Error loading icon '{filename}' from '{icon_path}': {e}")
        pass # No icons are actively displayed in the current UI

    def load_images(self) -> None:
        '''
        Scans the `image_folder` (and its subdirectories) for supported image files.
        Populates `self.images` with a sorted list of Path objects.
        Supported extensions: .png, .jpg, .jpeg, .gif, .bmp, .tiff, .webp.
        Hidden files (starting with '.') are ignored.
        '''
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
        self.images = [] # Reset image list

        if not self.image_folder.exists():
            logger.error(f"The specified image folder '{self.image_folder}' does not exist.")
            return
        if not self.image_folder.is_dir():
            logger.error(f"The path '{self.image_folder}' is not a directory.")
            return

        logger.info(f"Scanning for images in: {self.image_folder}")
        # os.walk is an alternative, but Path.rglob is often more concise for this
        raw_image_list = [
            item for item in self.image_folder.rglob('*') # rglob searches recursively
            if item.is_file() and \
               item.name.lower().endswith(image_extensions) and \
               not item.name.startswith('.') # Ignore hidden files
        ]

        if raw_image_list:
            self.images = sorted(raw_image_list) # Initial sort by full path (name)
            logger.info(f"Found {len(self.images)} images. Initial sort by path.")
        else:
            logger.warning(f"No images found in '{self.image_folder}' with supported extensions: {image_extensions}")

    def preload_next_images(self, count: int | None = None) -> None:
        '''
        Preloads the next N images into memory for faster display (N configurable).
        Args:
            count (int | None): The number of subsequent images to attempt to preload. If None, uses self.preload_count.
        '''
        if not self.images:
            return

        if count is None:
            count = self.preload_count

        indices_to_preload = []
        # Determine which images (by index) need preloading
        for i in range(1, count + 1):
            next_idx = (self.current_index + i) % len(self.images)
            if next_idx not in self.preloaded_images: # Only if not already in cache
                indices_to_preload.append(next_idx)
            # Stop preloading if we are at the end of the list and not looping
            if not self.loop and (self.current_index + i) >= (len(self.images) -1):
                break
            if len(indices_to_preload) >= count:
                break

        # Load the identified images
        for index_to_load in indices_to_preload:
            if index_to_load in self.preloaded_images:
                continue # Double check
            image_path = self.images[index_to_load]
            try:
                image = Image.open(image_path)
                image.load() # Force loading image data into memory
                self.preloaded_images[index_to_load] = image
                logger.debug(f"Preloaded image {index_to_load + 1}/{len(self.images)}: {image_path.name}")
            except Exception as e:
                logger.error(f"Error preloading image '{image_path.name}' (index {index_to_load}): {e}")
                if index_to_load in self.preloaded_images:
                    del self.preloaded_images[index_to_load]

        # Cache eviction strategy: remove images "far" from the current one.
        # Keeps a window of `count * 2` images before and after the current image.
        keys_to_keep = set()
        if self.images:
            preload_window_size = count * 2
            for i in range(-preload_window_size, preload_window_size + 1):
                idx_to_keep = (self.current_index + i + len(self.images)) % len(self.images)
                keys_to_keep.add(idx_to_keep)

        current_preloaded_keys = list(self.preloaded_images.keys())
        for key in current_preloaded_keys:
            if key not in keys_to_keep:
                del self.preloaded_images[key]

        # Affichage évolutif du nombre d'images préchargées (pour suivi dynamique)
        if not hasattr(self, '_last_buffer_count') or self._last_buffer_count != len(self.preloaded_images):
            logger.info(f"[Préchargement] Images en mémoire : {len(self.preloaded_images)}")
            self._last_buffer_count = len(self.preloaded_images)

    def on_resize(self, event: tk.Event) -> None:
        '''
        Handles the window resize event (<Configure>).
        It schedules a redraw of the current image to fit the new window size.
        Uses a debouncing mechanism to avoid excessive redraws during rapid resizing.

        Args:
            event (tk.Event): The Tkinter Configure event, containing new width and height.
        '''
        # Only respond to resize events from the main window, not child widgets
        if event.widget == self.window:
            logger.debug(f"Window resized to {event.width}x{event.height}. Scheduling image redraw.")
            
            # Debounce: if a resize job is already scheduled, cancel it
            if self._resize_job:
                self.window.after_cancel(self._resize_job)
            
            # Schedule the redraw after a short delay (e.g., 250ms)
            # Only redraw if the new size is somewhat practical
            if event.width > 50 and event.height > 50 : # Basic sanity check for window dimensions
                 self._resize_job = self.window.after(250, lambda: self.show_image(self.current_index, force_reload=False))
            else:
                 logger.debug("Resize event with very small dimensions, image redraw deferred.")

    def show_image(self, index: int, force_reload: bool = False) -> None:
        '''
        Displays the image at the specified index on the canvas.
        Handles image loading (from cache or disk), resizing, brightness adjustment,
        and GIF animation. Also updates HUD and schedules next image if timer is running.

        Args:
            index (int): The 0-based index of the image to display from `self.images`.
            force_reload (bool): If True, reloads the image from disk even if it's in the
                                 preload cache. Useful for brightness changes. Defaults to False.
        '''
        if not self.images:
            logger.warning("Show_image: No images available to display.")
            self.canvas.delete("all") # Clear canvas
            if self.canvas.winfo_width() > 1 and self.canvas.winfo_height() > 1:
                self.canvas.create_text(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2,
                                        text="No images found.", fill="white", font=("Helvetica", 16))
            return

        # Cancel any pending slideshow advancement or GIF animation from the previous image
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if self._gif_animation_after_id:
            self.window.after_cancel(self._gif_animation_after_id)
            self._gif_animation_after_id = None

        # Check for auto-stop condition
        if self.auto_stop and self.stop_time and time.time() >= self.stop_time:
            logger.info("Slideshow timer reached auto-stop time.")
            self.timer_running = False # Stop the timer
            self.update_hud() # Reflect paused state in HUD
            return # Do not proceed to show new image or schedule next

        # Validate and normalize the index
        if not (0 <= index < len(self.images)):
            logger.error(f"Show_image: Invalid image index {index} for {len(self.images)} images. Resetting to 0.")
            index = 0 if self.images else -1 # Fallback to 0 or -1 if list became empty
            if index == -1 : # Should be caught by the initial `if not self.images`
                self.quit() # No images left, critical state
                return
        self.current_index = index
        image_path = self.images[self.current_index]
        logger.info(f"Showing image {self.current_index + 1}/{len(self.images)}: '{image_path.name}'")

        try:
            pil_image: Image.Image | None = None
            # Attempt to get image from preload cache
            if not force_reload and self.current_index in self.preloaded_images:
                pil_image = self.preloaded_images[self.current_index]
                logger.debug(f"Using preloaded image: {image_path.name}")
            else: # Load from disk
                pil_image = Image.open(image_path)
                pil_image.load() # Ensure image data is fully loaded
                self.preloaded_images[self.current_index] = pil_image # Update cache
                logger.debug(f"Loaded image from disk (force_reload={force_reload}): {image_path.name}")
            
            # Get current canvas dimensions for resizing
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            # If canvas is not yet properly sized (e.g., during startup), schedule a retry
            if canvas_width <= 1 or canvas_height <= 1:
                logger.debug(f"Canvas not ready for image display (size: {canvas_width}x{canvas_height}). Scheduling redraw.")
                self.after_id = self.window.after(100, lambda: self.show_image(self.current_index, force_reload))
                return

            # Prepare image for display: resize and adjust brightness
            resized_image = self.resize_image(pil_image, canvas_width, canvas_height)
            # Apply brightness adjustment to a copy to avoid altering the cached PIL image
            adjusted_image = self.adjust_brightness(resized_image.copy()) 

            self.canvas.delete("all") # Clear canvas of previous image, HUD, info

            # Handle animated GIFs
            if getattr(pil_image, "is_animated", False) and pil_image.n_frames > 1:  # type: ignore[attr-defined]
                logger.debug(f"Processing animated GIF: {image_path.name} ({pil_image.n_frames} frames)")  # type: ignore[attr-defined]
                self._animate_gif_frames = []
                self._animate_gif_durations = []
                for frame_pil in ImageSequence.Iterator(pil_image):
                    # Each frame needs to be processed (converted, resized, brightness adjusted)
                    frame_rgba = frame_pil.copy().convert("RGBA") # Ensure RGBA for PhotoImage
                    frame_resized = self.resize_image(frame_rgba, canvas_width, canvas_height)
                    frame_adjusted = self.adjust_brightness(frame_resized) # Apply brightness to each frame
                    self._animate_gif_frames.append(ImageTk.PhotoImage(frame_adjusted))
                    self._animate_gif_durations.append(frame_pil.info.get('duration', 100)) # Frame duration
                
                if self._animate_gif_frames:
                    self._animate_gif_idx = 0 # Reset frame counter
                    self.animate_gif_next_frame() # Start animation loop
                else: # Fallback if GIF processing fails
                    logger.warning(f"Failed to process frames for GIF {image_path.name}. Displaying as static.")
                    self.display_static_image(adjusted_image, canvas_width, canvas_height)
            else: # Static image
                self.display_static_image(adjusted_image, canvas_width, canvas_height)

            self.update_hud() # Redraw the HUD
            if self.info_displayed: # If info overlay is active, redraw it
                self.display_image_info(image_path)

        except FileNotFoundError:
            logger.error(f"Image file not found: {image_path}. Removing from list.")
            self.images.pop(self.current_index) # Remove missing image
            if self.current_index in self.preloaded_images:
                del self.preloaded_images[self.current_index]
            # Adjust favorite indices
            self.favorites = [idx if idx < self.current_index else idx - 1 for idx in self.favorites if idx != self.current_index]
            
            if not self.images: # No images left
                logger.error("No more images to display after file not found. Closing application.")
                messagebox.showerror("Error", "The image file was not found or became inaccessible.\nNo more images to display.", parent=self.window)
                self.window.after(100, self.quit) # Schedule quit
                return
            # Show next available image (or current if list shortened but index is still valid)
            self.show_image(min(self.current_index, len(self.images) - 1))
            return
        except Exception as e:
            logger.error(f"Unhandled error displaying image '{image_path.name}': {e}", exc_info=True)
            # Attempt to gracefully move to the next image if in auto-play mode
            if self.timer_running:
                self.after_id = self.window.after(100, self.next_image_auto) # Try next image quickly
            return

        # Preload images for the next transition
        self.preload_next_images()  # Uses new default

        # Schedule the next image if the timer is running and not currently in a GIF animation loop
        # (GIF loop handles its own timing and can trigger next_image_auto upon completion)
        if self.timer_running and not (hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id) :
             if not (getattr(pil_image, "is_animated", False) and pil_image.n_frames > 1):  # type: ignore[attr-defined]  # If not a GIF currently animating
                 self.after_id = self.window.after(int(self.delay * 1000), self.next_image_auto)


    def display_static_image(self, image: Image.Image, canvas_width: int, canvas_height: int) -> None:
        '''
        Converts a PIL Image to PhotoImage and displays it on the canvas.
        The image is centered on the canvas.

        Args:
            image (Image.Image): The PIL Image object to display (already resized and brightness-adjusted).
            canvas_width (int): The current width of the canvas.
            canvas_height (int): The current height of the canvas.
        '''
        try:
            # Convert PIL Image to Tkinter PhotoImage
            photo = ImageTk.PhotoImage(image)
            # Display image on canvas, centered
            self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo, anchor=tk.CENTER, tags="image")
            # IMPORTANT: Keep a reference to the PhotoImage to prevent garbage collection
            self.canvas.image = photo  # type: ignore[attr-defined]
        except Exception as e:
            # Log error if PhotoImage creation or display fails
            logger.error(f"Error creating or displaying static PhotoImage: {e}", exc_info=True)


    def animate_gif_next_frame(self) -> None:
        '''
        Displays the next frame of an animated GIF.
        This method schedules itself to run for subsequent frames, creating an animation loop.
        It relies on instance attributes `_animate_gif_frames`, `_animate_gif_durations`, and `_animate_gif_idx`.
        '''
        # Ensure animation data is available and valid
        if not hasattr(self, '_animate_gif_frames') or not self._animate_gif_frames or self._animate_gif_idx >= len(self._animate_gif_frames) :
            logger.debug("GIF animation data missing or index out of bounds. Stopping animation.")
            if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id:
                self.window.after_cancel(self._gif_animation_after_id)
                self._gif_animation_after_id = None
            return

        # If the main slideshow timer has scheduled a new image, it takes precedence over GIF animation
        if self.after_id: 
            logger.debug("Main slideshow timer triggered during GIF animation. Stopping GIF to change image.")
            if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id:
                self.window.after_cancel(self._gif_animation_after_id)
                self._gif_animation_after_id = None
            return 

        current_frame_photoimage = self._animate_gif_frames[self._animate_gif_idx]
        current_frame_duration_ms = self._animate_gif_durations[self._animate_gif_idx]

        # Clear only the previous image frame from the canvas
        self.canvas.delete("image") 
        # Display the current frame
        if self.canvas.winfo_width() > 1 and self.canvas.winfo_height() > 1 : # Ensure canvas is valid
            self.canvas.create_image(
                self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                image=current_frame_photoimage, anchor=tk.CENTER, tags="image"
            )
            # Keep a reference to the current frame's PhotoImage
            self.canvas.image = current_frame_photoimage  # type: ignore[attr-defined]

        # Move to the next frame index, looping if necessary
        self._animate_gif_idx = (self._animate_gif_idx + 1) % len(self._animate_gif_frames)
        
        # Cancel any previously scheduled call for this GIF's next frame
        if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id:
            self.window.after_cancel(self._gif_animation_after_id)
            self._gif_animation_after_id = None # Clear the old ID

        # Logic for continuing GIF or transitioning to next image:
        if self.timer_running and self._animate_gif_idx == 0: 
            # GIF completed a full loop AND slideshow timer is running:
            # Schedule the *next image* based on the main slideshow delay.
            # The current GIF will stop.
            logger.debug(f"GIF loop completed. Scheduling next image with delay {self.delay}s.")
            self.after_id = self.window.after(int(self.delay * 1000), self.next_image_auto)
        else: 
            # Continue GIF animation: schedule the next frame of the *current* GIF.
            # This happens if timer is paused, or if GIF hasn't completed a loop.
            self._gif_animation_after_id = self.window.after(current_frame_duration_ms, self.animate_gif_next_frame)


    def resize_image(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        '''
        Resizes a PIL Image to fit within `target_width` and `target_height`,
        maintaining its original aspect ratio.

        Args:
            image (Image.Image): The original PIL Image object.
            target_width (int): The maximum width for the resized image.
            target_height (int): The maximum height for the resized image.

        Returns:
            Image.Image: The resized PIL Image. Returns a copy of original if resizing fails or is not needed.
        '''
        # Avoid issues with zero or negative target dimensions
        if target_width <= 0 or target_height <= 0:
            logger.warning(f"Resize_image: Invalid target dimensions ({target_width}x{target_height}). Returning original.")
            return image.copy()

        original_width, original_height = image.width, image.height
        # Avoid division by zero if original image dimensions are invalid
        if original_width == 0 or original_height == 0:
            logger.warning(f"Resize_image: Invalid original image dimensions ({original_width}x{original_height}).")
            return image.copy()
        
        # Calculate aspect ratios
        image_aspect_ratio = original_width / original_height
        target_aspect_ratio = target_width / target_height
        
        new_width, new_height = target_width, target_height

        # Determine new dimensions based on aspect ratios
        if image_aspect_ratio > target_aspect_ratio:
            # Image is wider than target aspect ratio (limited by width)
            new_height = int(new_width / image_aspect_ratio)
        else:
            # Image is taller or has the same aspect ratio as target (limited by height)
            new_width = int(new_height * image_aspect_ratio)
        
        # Ensure new dimensions are at least 1x1 pixels
        new_width = max(1, new_width)
        new_height = max(1, new_height)

        # Select resampling filter (LANCZOS is good for downscaling)
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS  # type: ignore[attr-defined]  # Pillow 9.1.0+
        
        try:
            #logger.debug(f"Resizing image from {image.size} to ({new_width}, {new_height})")
            return image.resize((new_width, new_height), resample_filter)
        except Exception as e:
            logger.error(f"Error during image resize from {image.size} to ({new_width},{new_height}): {e}")
            return image.copy() # Return a copy of the original on failure

    def adjust_brightness(self, image: Image.Image) -> Image.Image:
        '''
        Adjusts the brightness of a PIL Image using `ImageEnhance.Brightness`.

        Args:
            image (Image.Image): The PIL Image to adjust.

        Returns:
            Image.Image: The brightness-adjusted PIL Image. If brightness is 1.0 (no change)
                         or if an error occurs, the original image (or a copy) is returned.
        '''
        if self.brightness == 1.0: # No adjustment needed
            return image # Return the original image directly (not a copy unless downstream needs it)

        try:
            img_to_enhance = image
            original_mode = image.mode

            # Brightness enhancer works best on RGB. Handle other modes.
            if original_mode == 'P': # Palette mode
                img_to_enhance = image.convert('RGBA') if 'transparency' in image.info else image.convert('RGB')
            elif original_mode == 'L': # Greyscale
                 pass # Brightness works on L
            elif original_mode not in ['RGB', 'RGBA', 'L']:
                 # For other modes, attempt conversion to RGB.
                 logger.debug(f"Adjust_brightness: Converting image from mode {original_mode} to RGB for enhancement.")
                 img_to_enhance = image.convert('RGB')
            
            # If image has an Alpha channel, preserve it
            if img_to_enhance.mode == 'RGBA':
                rgb_channels = img_to_enhance.convert('RGB')
                alpha_channel = img_to_enhance.split()[-1] # Get the alpha channel
                
                enhancer = ImageEnhance.Brightness(rgb_channels)
                enhanced_rgb = enhancer.enhance(self.brightness)
                
                return Image.merge('RGBA', (*enhanced_rgb.split(), alpha_channel))
            else: # For RGB or L modes (or those converted to RGB)
                enhancer = ImageEnhance.Brightness(img_to_enhance)
                return enhancer.enhance(self.brightness)

        except Exception as e:
            logger.warning(f"Could not adjust brightness for image (mode {image.mode}): {e}. Returning original.")
            return image # Return original on error

    def update_hud(self) -> None:
        '''
        Updates the Heads-Up Display (HUD) on the canvas.
        The HUD shows slideshow status (play/pause, image count, delay, etc.)
        and optionally a list of keyboard shortcuts. It's centered at the bottom.
        '''
        # Clear previous HUD elements to prevent overlap
        self.canvas.delete("hud_bg")    
        self.canvas.delete("hud_text")  

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Define minimum canvas dimensions for HUD to be practical
        MIN_CANVAS_WIDTH_FOR_HUD = 200 # Arbitrary minimum practical width for HUD text
        MIN_CANVAS_HEIGHT_FOR_HUD = 60 # Minimum height for a few lines of HUD
        if canvas_width < MIN_CANVAS_WIDTH_FOR_HUD or canvas_height < MIN_CANVAS_HEIGHT_FOR_HUD:
            logger.debug(f"Canvas too small ({canvas_width}x{canvas_height}) to draw HUD. Skipping update.")
            return

        # --- Gather HUD information strings ---
        play_status = "Playing" if self.timer_running else "Paused"
        loop_status = "Loop: On" if self.loop else "Loop: Off"
        auto_stop_status = "AutoStop: On" if self.auto_stop else "AutoStop: Off"
        if self.auto_stop and self.stop_time > 0: # If auto_stop is active and time is set
            time_remaining = max(0, int(self.stop_time - time.time()))
            auto_stop_status += f" ({time_remaining}s)"

        image_count_str = "No images"
        current_image_name = ""
        if self.images and 0 <= self.current_index < len(self.images): # Check if images list and index are valid
            image_path = self.images[self.current_index]
            image_count_str = f"{self.current_index + 1}/{len(self.images)}"
            if self.current_index in self.favorites:
                image_count_str += " ★" # Star symbol for favorited image
            
            current_image_name = image_path.name
            MAX_NAME_LEN_HUD = 40 # Max length for image name display in HUD
            if len(current_image_name) > MAX_NAME_LEN_HUD: # Truncate long names
                current_image_name = current_image_name[:MAX_NAME_LEN_HUD-3] + "..."
        
        delay_str = f"Delay: {self.delay:.1f}s"
        brightness_str = f"Bright: {self.brightness:.1f}"

        # Assemble HUD lines
        hud_lines = [
            f"{play_status} | {image_count_str}{' - ' + current_image_name if current_image_name else ''}", # Line 1: Play status, count, name
            f"{delay_str} | {brightness_str} | {loop_status} | {auto_stop_status}", # Line 2: Parameters
        ]

        # Add shortcut help text if toggled on
        if self.show_full_hud:
            shortcut_text = self.get_hud_shortcut_text()
            if shortcut_text: # Ensure it's not empty
                 hud_lines.append(shortcut_text) # Add as subsequent lines

        final_hud_text = "\n".join(filter(None, hud_lines)) # Join non-empty lines

        if not final_hud_text.strip(): # If HUD text is effectively empty, don't draw
            logger.debug("HUD text is empty, skipping HUD drawing.")
            return

        # --- Drawing parameters ---
        padding = 8 # Padding around the text block for the background rectangle
        font_size = 10
        hud_font = ("Helvetica", font_size, "bold")

        # Position for centered text at the bottom of the canvas
        text_x_position = canvas_width / 2 # Center horizontally
        text_y_position = canvas_height - padding # Y position from bottom, accounting for bg padding

        # Max width for the text block, using a percentage of canvas width to ensure it fits
        text_wrap_width = canvas_width * 0.85 # Use 85% of canvas width for text wrapping
        # Ensure a minimum practical width for wrapping, especially on small canvases
        if text_wrap_width < MIN_CANVAS_WIDTH_FOR_HUD * 0.8: 
             text_wrap_width = MIN_CANVAS_WIDTH_FOR_HUD * 0.8

        # --- Create HUD elements on canvas ---
        # Create the text item first
        text_item_id = self.canvas.create_text(
            text_x_position,              
            text_y_position, 
            anchor=tk.S, # Anchor South: text block's bottom-center point is at (x,y)
            text=final_hud_text,
            fill="white", # Text color
            font=hud_font, 
            tags="hud_text", # Tag for easy deletion/manipulation
            width=int(text_wrap_width), # Max width for text lines before wrapping
            justify=tk.CENTER # Justify multi-line text to the center
        )
        
        text_bbox = None
        try:
            # update_idletasks() can help ensure Tkinter has processed pending geometry changes
            # before bbox is called, leading to more accurate bounding box.
            self.canvas.update_idletasks() 
            text_bbox = self.canvas.bbox(text_item_id) # Get bounding box of the rendered text
        except tk.TclError: 
            # This can happen if the widget is being destroyed.
            logger.warning("TclError encountered while getting HUD text bounding box. Canvas may be shutting down.")

        if text_bbox:
            # Bounding box returns (x0, y0, x1, y1)
            x0, y0, x1, y1 = text_bbox
            # Create a background rectangle sized to the text plus padding
            bg_item_id = self.canvas.create_rectangle(
                x0 - padding, y0 - padding, x1 + padding, y1 + padding,
                fill="black",      # Solid black background for readability
                outline="#505050", # Dark grey outline for the background box
                tags="hud_bg"      # Tag for easy deletion
            )
            # Ensure the background rectangle is drawn *under* the text
            self.canvas.tag_lower(bg_item_id, text_item_id)
        else:
            # If bbox couldn't be determined, the background won't be drawn correctly.
            # This might happen if final_hud_text was empty or canvas not ready.
            logger.warning("Could not get bounding box for HUD text. HUD background might be missing or improperly sized.")


    def next_image_auto(self) -> None:
        '''
        Automatically advances to the next image in the slideshow.
        This is typically called by the `after` scheduler when `timer_running` is True.
        It respects the `loop` setting.
        '''
        if not self.images: # Should not happen if initial checks are done
            self.timer_running = False
            return

        if not self.loop and self.current_index >= len(self.images) - 1:
            # Reached the end of the list and looping is off
            self.timer_running = False # Stop the timer
            logger.info("End of slideshow reached (looping is off).")
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None # Clear just in case
            self.update_hud() # Reflect paused state
            return
        
        # Calculate next index, wrapping around if looping
        next_idx = (self.current_index + 1) % len(self.images)
        self.show_image(next_idx)


    def toggle_timer(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the slideshow timer on (play) or off (pause).
        If resuming, it re-evaluates the current image display which schedules the next.
        If pausing, it cancels any pending automatic advancement.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.timer_running = not self.timer_running
        logger.info(f"Slideshow timer {'started (Playing)' if self.timer_running else 'paused'}.")

        if self.timer_running:
            # If resuming play:
            # Cancel any old main timer (after_id) to avoid multiple timers.
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None
            
            # Re-calling show_image for the current image will:
            # 1. If it's a GIF, its animation might resume or continue.
            # 2. If it's a static image, it will schedule `next_image_auto` via `self.after_id`.
            # This ensures the delay is respected from the moment of resuming.
            self.show_image(self.current_index) 
        else: 
            # If pausing:
            # Cancel the main slideshow advancement timer.
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None
            # Also cancel any ongoing GIF frame animation timer.
            if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id:
                self.window.after_cancel(self._gif_animation_after_id)
                self._gif_animation_after_id = None # Clear the ID as it's no longer valid
        
        self.update_hud() # Reflect the new play/pause state


    def next_image(self, event: tk.Event | None = None) -> None:
        '''
        Manually advances to the next image in the slideshow.
        This action pauses the automatic slideshow timer.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images:
            return # No images to navigate

        self.timer_running = False # Manual navigation pauses the timer
        # Cancel any pending auto-advance or GIF animation
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id:
            self.window.after_cancel(self._gif_animation_after_id)
            self._gif_animation_after_id = None
        
        next_idx = (self.current_index + 1) % len(self.images)
        # If not looping and currently on the last image, clicking next does nothing more.
        if not self.loop and self.current_index == len(self.images) - 1:
            logger.info("Already at the last image (looping is off).")
        else:
            self.show_image(next_idx)
        self.update_hud() # Reflect paused state and new image index


    def previous_image(self, event: tk.Event | None = None) -> None:
        '''
        Manually goes to the previous image in the slideshow.
        This action pauses the automatic slideshow timer.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images:
            return # No images to navigate

        self.timer_running = False # Manual navigation pauses the timer
        # Cancel any pending auto-advance or GIF animation
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id:
            self.window.after_cancel(self._gif_animation_after_id)
            self._gif_animation_after_id = None

        # Calculate previous index, wrapping around correctly
        prev_idx = (self.current_index - 1 + len(self.images)) % len(self.images)
        
        # If not looping and currently on the first image, clicking previous does nothing more.
        if not self.loop and self.current_index == 0 :
             logger.info("Already at the first image (looping is off).")
        else:
            self.show_image(prev_idx)
        self.update_hud() # Reflect paused state and new image index


    def increase_speed(self, event: tk.Event | None = None) -> None: 
        '''
        Increases slideshow speed by DECREASING the delay between images.
        Minimum delay is capped at 0.1 seconds.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.delay = max(0.1, round(self.delay - 0.5, 1)) # Decrease delay, min 0.1s
        logger.info(f"Slideshow delay decreased to: {self.delay:.1f}s")
        # If timer is running, reschedule the next auto-advance with the new delay
        if self.timer_running and self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = self.window.after(int(self.delay * 1000), self.next_image_auto)
        self.update_hud()


    def decrease_speed(self, event: tk.Event | None = None) -> None: 
        '''
        Decreases slideshow speed by INCREASING the delay between images.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.delay = round(self.delay + 0.5, 1) # Increase delay
        logger.info(f"Slideshow delay increased to: {self.delay:.1f}s")
        # If timer is running, reschedule with new delay
        if self.timer_running and self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = self.window.after(int(self.delay * 1000), self.next_image_auto)
        self.update_hud()


    def toggle_fullscreen(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the application's fullscreen mode.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.is_fullscreen = not self.is_fullscreen
        self.window.attributes('-fullscreen', self.is_fullscreen)
        logger.info(f"Fullscreen mode: {'Enabled' if self.is_fullscreen else 'Disabled'}")
        self.update_hud() # HUD might change appearance or content based on fullscreen


    def toggle_always_on_top(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the 'always on top' attribute for the application window.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.always_on_top = not self.always_on_top
        self.window.attributes('-topmost', self.always_on_top)
        logger.info(f"Window 'Always on Top': {'Enabled' if self.always_on_top else 'Disabled'}")
        # No direct HUD update needed unless it displays this status


    def toggle_auto_stop(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the auto-stop feature. If enabled, the slideshow will stop
        playing automatically after `self.auto_stop_delay` seconds.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.auto_stop = not self.auto_stop
        if self.auto_stop:
            self.stop_time = time.time() + self.auto_stop_delay # Set future stop time
            logger.info(f"Auto-stop enabled. Slideshow will stop in approximately {self.auto_stop_delay} seconds.")
        else:
            self.stop_time = 0.0 # Clear stop time
            logger.info("Auto-stop disabled.")
        self.update_hud() # Reflect change in HUD


    def toggle_image_info(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the display of detailed information (metadata, EXIF) about the current image.
        The information is shown as an overlay on the canvas.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.info_displayed = not self.info_displayed
        if self.info_displayed:
            # If toggled on, display info for the current image
            if self.images and 0 <= self.current_index < len(self.images):
                self.display_image_info(self.images[self.current_index])
            else: # No valid image to display info for, so revert toggle
                logger.warning("Image info display toggle: No current image to display info for.")
                self.info_displayed = False 
        else:
            # If toggled off, clear any existing info display
            self.clear_image_info()
        # The HUD itself doesn't change, but the canvas content does.
        # `show_image` also calls `display_image_info` if `self.info_displayed` is true.


    def display_image_info(self, image_path: Path) -> None:
        '''
        Displays detailed information about the specified image_path on the canvas.
        This includes file stats and available EXIF data. The info is shown in the top-left.

        Args:
            image_path (Path): The Path object of the image file to get information from.
        '''
        self.clear_image_info() # Clear any previously displayed info first

        try:
            if not image_path.exists():
                logger.warning(f"Display_image_info: File not found: {image_path}")
                self.canvas.create_text(50, 50, text=f"Info: File not found\n{image_path.name}", fill="red", anchor=tk.NW, tags="info_text")
                return

            file_stats = image_path.stat() # Get file system statistics
            pil_image = Image.open(image_path) # Open image with Pillow to access properties
            pil_image.load() # Ensure image data and EXIF are loaded

            # Gather information into a list of strings
            info_items = [
                f"File: {image_path.name}",
                f"Path: {str(image_path.parent)[:80]}{'...' if len(str(image_path.parent)) > 80 else ''}", # Truncate long paths
                f"Resolution: {pil_image.width}x{pil_image.height}",
                f"Size: {file_stats.st_size / (1024 * 1024):.2f} MB", # Size in MB
                f"Created: {time.ctime(file_stats.st_ctime)}",
                f"Modified: {time.ctime(file_stats.st_mtime)}",
                f"Format: {pil_image.format}",
            ]

            # Attempt to get EXIF data
            exif_data = pil_image.getexif() # Standard way to get EXIF IFD
            if exif_data:
                info_items.append("\nEXIF Data (selected):")
                exif_display_count = 0
                max_exif_to_display = 10 # Limit number of EXIF tags shown
                for tag_id, value in exif_data.items():
                    if exif_display_count >= max_exif_to_display:
                        info_items.append("  ... (more EXIF data available)")
                        break
                    tag_name = TAGS.get(tag_id, tag_id) # Get human-readable tag name
                    
                    # Decode bytes values, truncate long strings
                    value_str = str(value)
                    if isinstance(value, bytes):
                        value_str = value.decode(errors='replace') # Handle byte strings
                    if len(value_str) > 55:
                        value_str = value_str[:52] + "..." # Truncate long values
                    
                    info_items.append(f"  {tag_name}: {value_str}")
                    exif_display_count += 1
            
            info_text_content = "\n".join(info_items)
            
            # --- Draw info box on canvas (top-left) ---
            padding = 10 # Padding inside the info box background
            text_x_start, text_y_start = padding + 10, padding + 10 # Position of text block

            # Create the text item
            info_text_id = self.canvas.create_text(
                text_x_start, text_y_start, anchor=tk.NW, text=info_text_content,
                fill="white", font=("Helvetica", 9), # Slightly smaller font for info box
                justify=tk.LEFT, tags="info_text"
            )
            
            # Create a background for the text
            try:
                self.canvas.update_idletasks() # Ensure bbox is accurate
                bbox = self.canvas.bbox(info_text_id) # Get actual bounds of the text
                if bbox:
                    x0,y0,x1,y1 = bbox
                    # Create semi-transparent black background
                    info_bg_id = self.canvas.create_rectangle(
                        x0 - padding, y0 - padding, x1 + padding, y1 + padding,
                        fill="black", outline="#444444", tags="info_background"
                    )
                    self.canvas.tag_lower(info_bg_id, info_text_id) # Place background behind text
                else: # If no bbox, text might be empty or invalid, remove the item
                    self.canvas.delete(info_text_id) 
            except tk.TclError:
                logger.warning("TclError getting info_text bbox during display_image_info.")

        except Exception as e:
            logger.error(f"Error displaying image info for '{image_path.name}': {e}", exc_info=True)
            self.canvas.create_text(50, 50, text=f"Error loading info for\n{image_path.name}", fill="orange", anchor=tk.NW, tags="info_text")


    def clear_image_info(self) -> None:
        '''
        Clears the image information display (text and background) from the canvas.
        '''
        self.canvas.delete("info_background")
        self.canvas.delete("info_text")
        logger.debug("Cleared image info display.")


    def increase_brightness(self, event: tk.Event | None = None) -> None:
        '''
        Increases the display brightness for images.
        Brightness factor is capped at 2.0 (double brightness).
        Forces a reload of the current image to apply the new brightness.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.brightness = min(round(self.brightness + 0.1, 1), 2.0) # Increase, cap at 2.0
        logger.info(f"Image brightness increased to: {self.brightness:.1f}")
        self.show_image(self.current_index, force_reload=True) # Force reload to re-apply brightness
        self.update_hud() # Update HUD to show new brightness value


    def decrease_brightness(self, event: tk.Event | None = None) -> None:
        '''
        Decreases the display brightness for images.
        Brightness factor is capped at 0.1 (very dim).
        Forces a reload of the current image to apply the new brightness.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.brightness = max(round(self.brightness - 0.1, 1), 0.1) # Decrease, cap at 0.1
        logger.info(f"Image brightness decreased to: {self.brightness:.1f}")
        self.show_image(self.current_index, force_reload=True) # Force reload
        self.update_hud()


    def toggle_loop(self, event: tk.Event | None = None) -> None:
        '''
        Toggles the slideshow looping behavior (whether to restart after the last image).

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        self.loop = not self.loop
        logger.info(f"Slideshow looping: {'Enabled' if self.loop else 'Disabled'}")
        self.update_hud() # Reflect change in HUD


    def shuffle_images(self, event: tk.Event | None = None) -> None:
        '''
        Randomly shuffles the order of images in the slideshow.
        Preloaded image cache is cleared. Favorite image indices are re-mapped if possible.
        Resets slideshow to the first image of the new shuffled list.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images:
            logger.warning("Shuffle: No images to shuffle.")
            return
        
        logger.info("Shuffling images.")
        # Preserve favorites by remembering their paths before shuffle
        favorited_paths = {self.images[idx] for idx in self.favorites if 0 <= idx < len(self.images)}
        
        random.shuffle(self.images) # Shuffle the list of image paths in-place
        
        self.preloaded_images.clear() # Preload cache is invalidated by shuffle

        # Rebuild favorites based on new indices of the (now shuffled) paths
        self.favorites = sorted([i for i, img_path in enumerate(self.images) if img_path in favorited_paths])
        logger.info(f"{len(self.favorites)} favorites re-mapped after shuffle.")

        self.current_index = 0 # Start from the beginning of the shuffled list
        self.show_image(self.current_index) # Display the new first image
        self.update_hud()


    def sort_images(self, event: tk.Event | None = None) -> None:
        '''
        Sorts images by their file creation time (st_ctime).
        Toggles between ascending (oldest first) and descending (newest first) order.
        Preload cache is cleared. Favorites are re-mapped. Resets to the first image.

        Args:
            event (tk.Event | None): The Tkinter event. Defaults to None.
        '''
        if not self.images:
            logger.warning("Sort: No images to sort.")
            return

        # Preserve favorites by path
        favorited_paths = {self.images[idx] for idx in self.favorites if 0 <= idx < len(self.images)}
        
        try:
            # `self.sort_ascending` indicates the order for the *current* sort operation
            # If True, sort ascending (oldest first). Then toggle for next time.
            current_sort_order_is_ascending = self.sort_ascending
            self.images.sort(key=lambda p: p.stat().st_ctime, reverse=not current_sort_order_is_ascending)
            
            sort_order_message = "ascending (oldest first)" if current_sort_order_is_ascending else "descending (newest first)"
            logger.info(f"Images sorted by creation time: {sort_order_message}.")
            
            self.sort_ascending = not self.sort_ascending # Toggle for the *next* sort operation
        except Exception as e:
            logger.error(f"Error sorting images by ctime: {e}. Image order may be unchanged.")
            return # Avoid further operations if sort failed

        self.preloaded_images.clear() # Cache invalidated

        # Rebuild favorites based on new indices
        self.favorites = sorted([i for i, img_path in enumerate(self.images) if img_path in favorited_paths])
        logger.info(f"{len(self.favorites)} favorites re-mapped after sorting.")

        self.current_index = 0 # Go to the first image in the sorted list
        self.show_image(self.current_index)
        self.update_hud()


    def get_hud_shortcut_text(self) -> str:
        '''
        Generates the multi-line string of keyboard shortcuts for display in the HUD.
        Shortcuts are grouped for better readability.

        Returns:
            str: A formatted string of keyboard shortcuts.
        '''
        # List of shortcuts with brief descriptions
        shortcuts = [
            "Spc: Play/Pause", "←/→: Prev/Next", "Q/Esc: Quit", "H: Toggle Help",
            "S: Shuffle", "T: Sort(Time)", "J: Jump", "F: Fullscreen",
            "+/-: Speed", "L/K: Brightness", "I: Image Info", "B: Loop",
            "A: AutoStop", "W: AlwaysOnTop", "Z: Favorite ★", "Y: Yoink (macOS)"
        ]
        
        lines = []
        items_per_line = 4 # Adjust this to control how many shortcuts appear on each line
        for i in range(0, len(shortcuts), items_per_line):
            # Join a slice of shortcuts with a wider separator for clarity
            lines.append("  |  ".join(shortcuts[i:i+items_per_line]))

        return "\n".join(lines) # Each group on a new line


    def on_click(self, event: tk.Event) -> None:
        '''
        Handles mouse click events on the canvas.
        Currently, a left-click (Button-1) toggles the slideshow timer (play/pause).

        Args:
            event (tk.Event): The Tkinter mouse click event. `event.num` gives button number.
        '''
        if event.num == 1: # Left mouse button
            self.toggle_timer()
        # Other buttons (e.g., event.num == 3 for right-click) could be handled here.


    def on_scroll(self, event: tk.Event) -> None:
        '''
        Handles mouse scroll wheel events on the canvas.
        Scrolling up typically goes to the previous image, scrolling down to the next.
        Pauses the timer on scroll.

        Args:
            event (tk.Event): The Tkinter mouse scroll event.
                              `event.delta` (Windows/macOS) or `event.num` (X11) indicates direction.
        '''
        # event.delta: positive for scroll up (usually), negative for scroll down on Win/macOS.
        # event.num: 4 for scroll up, 5 for scroll down on X11/Linux systems.
        if event.delta > 0 or (hasattr(event, 'num') and event.num == 4): # Scroll Up
            self.previous_image()
        elif event.delta < 0 or (hasattr(event, 'num') and event.num == 5): # Scroll Down
            self.next_image()


    def quit(self, event: tk.Event | None = None) -> None:
        '''
        Performs cleanup (saves favorites, cancels pending jobs) and closes the application.

        Args:
            event (tk.Event | None): The Tkinter event (e.g., key press). Defaults to None.
        '''
        logger.info("Quit sequence initiated...")
        self.save_favorites() # Save any changes to favorites

        # Cancel any pending 'after' jobs to prevent errors during shutdown
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if hasattr(self, '_gif_animation_after_id') and self._gif_animation_after_id: # Check if attribute exists
            self.window.after_cancel(self._gif_animation_after_id)
            self._gif_animation_after_id = None
        if hasattr(self, '_resize_job') and self._resize_job: # Check if attribute exists
            self.window.after_cancel(self._resize_job)
            self._resize_job = None
        
        logger.info("Attempting to destroy Tkinter window.")
        try:
            # self.window.quit() # Stops Tkinter mainloop, can be used before destroy
            if self.window.winfo_exists(): # Check if window still exists before destroying
                 self.window.destroy() # Destroy the main window and its children
        except tk.TclError as e:
            # This can happen if the window is already in the process of being destroyed.
            logger.warning(f"TclError during window destroy (possibly already destroyed or during shutdown): {e}")
        logger.info("Application closed.")
        # sys.exit(0) # Usually not needed if mainloop exits cleanly after destroy.
                      # Can be useful in some complex app structures or if launched as subprocess.


# --- Main function encapsulating the execution block ---
def main():
    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(
        description="A feature-rich image slideshow application with Tkinter.",
        formatter_class=argparse.RawTextHelpFormatter # For better formatting of help text
    )
    parser.add_argument(
        'image_folder', 
        type=str, 
        help="Path to the folder containing images to display."
    )
    parser.add_argument(
        '--delay', '-d', 
        type=float, 
        default=1.0, 
        help="Delay between images in seconds during automatic slideshow. Default: 1.0s."
    )
    parser.add_argument(
        '--auto-stop', '-as', 
        type=int, 
        default=None, # Auto-stop is off by default unless a duration is given
        metavar='SECONDS', 
        help="Automatically stop the slideshow after SECONDS. Default: Off."
    )
    parser.add_argument(
        '--start-index', '-idx', 
        type=int, 
        default=0, 
        metavar='N', 
        help="Start the slideshow from image index N (0-based). Default: 0."
    )
    parser.add_argument(
        '--log-level', 
        type=str, 
        default='INFO', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
        help="Set the logging level for console output. Default: INFO."
    )
    parser.add_argument(
        '--preload-count',
        type=int,
        default=20,
        metavar='N',
        help="Number of images to preload ahead for smoothness (default: 20)"
    )
    parser.add_argument(
        '--shuffle', # Changed from --shuffle-on-start for brevity
        action='store_true', # Becomes True if flag is present, False otherwise
        help="Shuffle the order of images at startup."
    )
    args = parser.parse_args()

    # Validate arguments
    if args.start_index < 0:
        print("Error: --start-index cannot be negative.", file=sys.stderr)
        sys.exit(1) # Exit with an error code

    app_instance_window = None # Ensure variable is in scope for finally block
    app_instance = None      # Ensure app instance is in scope for finally block

    try:
        app_instance_window = tk.Tk() # Create the main Tkinter window
        # app_instance_window.withdraw() # Optionally hide window until fully initialized

        # Create and configure the application instance
        app_instance = ImageSlideshowApp(
            app_instance_window,
            args.image_folder,
            delay=args.delay,
            auto_stop_delay=args.auto_stop, # Pass the value; app handles None
            preload_count=args.preload_count,
            log_level=args.log_level
        )

        # If app initialization failed (e.g., no images found), it might have scheduled its own destruction.
        # Check if the window still exists before proceeding.
        if not app_instance_window.winfo_exists():
            logger.info("Main window was destroyed during app initialization (likely no images). Exiting.")
            sys.exit(1)
        
        # Apply command-line settings after app is initialized
        if args.shuffle:
            logger.info("Shuffling images on start as per command-line argument.")
            app_instance.shuffle_images() # This method also calls show_image

        # Set start index, ensuring it's valid for the (possibly shuffled) image list
        if 0 <= args.start_index < len(app_instance.images):
            app_instance.current_index = args.start_index
        elif args.start_index != 0 : # If a non-default start_index was given and is invalid
             logger.warning(f"Command-line start index {args.start_index} is out of bounds (max: {len(app_instance.images)-1}). Starting from image 0.")
             app_instance.current_index = 0 # Default to first image
        
        # Activate auto-stop if a duration was provided via CLI
        if args.auto_stop is not None: # CLI arg for auto_stop_delay implies auto_stop should be on
            app_instance.auto_stop = True
            # app_instance.auto_stop_delay is already set from constructor
            app_instance.stop_time = time.time() + app_instance.auto_stop_delay # Calculate when to stop
            logger.info(f"CLI: Auto-stop feature enabled for {app_instance.auto_stop_delay} seconds.")
            # HUD will be updated when show_image is called

        # Initial image display (if not already shown by shuffle_images)
        if not args.shuffle: # If shuffle didn't already call show_image
             app_instance.show_image(app_instance.current_index) 
        
        # app_instance_window.deiconify() # Make window visible if it was withdrawn
        app_instance_window.mainloop() # Start the Tkinter event loop

    except tk.TclError as e:
        # Catch TclErrors, often related to display server issues or Tk setup problems
        logger.critical(f"Tkinter TclError occurred: {e}. Ensure a display server (X11, Wayland, Aqua) is available and configured.", exc_info=True)
        print(f"Critical Tkinter Error: {e}. Could not initialize graphics. Please ensure a display server is available.", file=sys.stderr)
        if app_instance_window and app_instance_window.winfo_exists():
            app_instance_window.destroy()
        sys.exit(1)
    except FileNotFoundError as e: # Catch issues like image folder not found if not handled by Path lib early enough
        logger.critical(f"File system error, likely related to the image folder: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        if app_instance_window and app_instance_window.winfo_exists():
            app_instance_window.destroy()
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (Ctrl+C). Initiating shutdown.")
        # Graceful shutdown attempt handled in finally
    except Exception as e:
        # Catch any other unexpected exceptions during application setup or runtime
        logger.critical(f"An unexpected error occurred in the main execution block: {e}", exc_info=True)
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        if app_instance_window and app_instance_window.winfo_exists():
            app_instance_window.destroy()
        sys.exit(1)
    finally:
        # Ensure graceful shutdown if app instance was created
        if app_instance and app_instance_window and app_instance_window.winfo_exists():
            logger.info("Performing final cleanup via app.quit().")
            app_instance.quit() # Call the app's quit method for saving favorites, etc.
        elif app_instance_window and app_instance_window.winfo_exists(): # If app object not fully there, just destroy window
            logger.info("App instance not fully available, directly destroying window if it exists.")
            app_instance_window.destroy()
        logger.info("Application has finished execution.")

# --- Execution block calling the main function ---
if __name__ == '__main__':
    main()
