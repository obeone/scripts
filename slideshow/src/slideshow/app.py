from __future__ import annotations
"""
Main application class for the Image Slideshow.

This module defines the `ImageSlideshowApp` class, which serves as the central
orchestrator for the application. It manages the main window, application state,
and coordinates the interactions between the various sub-modules (controls,
display, image loading, etc.).
"""

import tkinter as tk
from tkinter import messagebox
import logging
import time
from pathlib import Path
from PIL import Image, ImageTk, ImageSequence

from . import config, controls, display, favorites, hud, image_loader, yoink, exif_utils
from .exceptions.slideshow_errors import ImageNotFound

logger = logging.getLogger(__name__)

class ImageSlideshowApp:
    """
    The main application class for the image slideshow.
    """

    def __init__(self, window: tk.Tk, image_folder: str, delay: float, auto_stop_delay: int | None):
        self.window = window
        self.image_folder = Path(image_folder).resolve()
        self.delay = float(delay)
        self.auto_stop_delay = auto_stop_delay if auto_stop_delay is not None else config.DEFAULT_AUTO_STOP_DELAY

        # Core state
        self.images: list[Path] = []
        self.current_index: int = 0
        self.preloaded_images: dict[int, Image.Image] = {}
        self.favorites: list[int] = []
        
        # Playback state
        self.timer_running: bool = True
        self.loop: bool = True
        self.after_id: str | None = None
        self.auto_stop: bool = auto_stop_delay is not None
        self.stop_time: float = 0.0
        if self.auto_stop:
            self.stop_time = time.time() + self.auto_stop_delay

        # Display state
        self.brightness: float = 1.0
        self.info_displayed: bool = False
        self.show_full_hud: bool = True
        self._current_photo_ref: ImageTk.PhotoImage | tk.PhotoImage | None = None
        self._resize_job: str | None = None

        # GIF animation state
        self._gif_animation_after_id: str | None = None
        self._animate_gif_frames: list[ImageTk.PhotoImage | tk.PhotoImage] = []
        self._animate_gif_durations: list[int] = []
        self._animate_gif_idx: int = 0

        # UI Elements
        self.canvas = tk.Canvas(self.window, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.setup()

    def setup(self) -> None:
        """
        Perform the initial setup of the application.

        This method loads images from the specified folder, initializes favorites,
        sets up the main window properties, and binds user controls.
        If no images are found, it displays an error and closes the application.
        """
        self.images = image_loader.load_images_from_folder(self.image_folder)
        if not self.images:
            messagebox.showerror("Error", "No valid images found in the specified folder.")
            self.window.after(50, self.window.destroy)
            return

        self.favorites = favorites.load_favorites(self.image_folder, len(self.images))
        
        self.window.title("Image Slideshow")
        self.is_fullscreen = True
        self.window.attributes('-fullscreen', self.is_fullscreen)
        self.always_on_top = False
        
        controls.bind_controls(self)
        self.show_image(0)

    def show_image(self, index: int, force_reload: bool = False) -> None:
        """
        Display the image at the given index.

        This is the core display function. It handles loading, resizing,
        and displaying the image on the canvas. It also manages GIF animations,
        updates the HUD, and preloads subsequent images.

        Args:
            index: The index of the image to display in the `self.images` list.
            force_reload: If True, forces the image to be reloaded from disk,
                          bypassing the cache.
        """
        if not self.images:
            return
        
        self.current_index = index % len(self.images)
        image_path = self.images[self.current_index]
        logger.info(f"Showing image {self.current_index + 1}/{len(self.images)}: '{image_path.name}'")

        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        if self._gif_animation_after_id:
            self.window.after_cancel(self._gif_animation_after_id)
            self._gif_animation_after_id = None

        try:
            pil_image = self.preloaded_images.get(self.current_index)
            if not pil_image or force_reload:
                pil_image = Image.open(image_path)
                pil_image.load()
                
                # Convert to RGB immediately after loading to prevent compatibility issues
                # RGB is the most reliable mode for all subsequent operations including ImageTk
                if pil_image.mode != 'RGB':
                    logger.debug(f"Converting loaded image from mode '{pil_image.mode}' to 'RGB' for maximum compatibility.")
                    # Handle transparency by adding a white background
                    if pil_image.mode in ('RGBA', 'LA') or 'transparency' in pil_image.info:
                        background = Image.new('RGB', pil_image.size, (255, 255, 255))
                        if pil_image.mode == 'P':
                            pil_image = pil_image.convert('RGBA')
                        background.paste(pil_image, mask=pil_image.split()[-1] if pil_image.mode in ('RGBA', 'LA') else None)
                        pil_image = background
                    else:
                        pil_image = pil_image.convert('RGB')
                
                self.preloaded_images[self.current_index] = pil_image

            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:
                self.after_id = self.window.after(100, lambda: self.show_image(self.current_index, force_reload))
                return

            resized_image = display.resize_image(pil_image, canvas_width, canvas_height)
            adjusted_image = display.adjust_brightness(resized_image, self.brightness)

            self.canvas.delete("all")

            is_animated = getattr(pil_image, "is_animated", False)
            n_frames = getattr(pil_image, "n_frames", 1)

            if is_animated and n_frames > 1:
                self._animate_gif_frames = []
                self._animate_gif_durations = []
                for frame_pil in ImageSequence.Iterator(pil_image):
                    frame_rgba = frame_pil.copy().convert("RGBA")
                    frame_resized = display.resize_image(frame_rgba, canvas_width, canvas_height)
                    frame_adjusted = display.adjust_brightness(frame_resized, self.brightness)
                    frame_photo = display.create_photoimage_robust(frame_adjusted)
                    if frame_photo:
                        self._animate_gif_frames.append(frame_photo)
                        self._animate_gif_durations.append(frame_pil.info.get('duration', 100))
                
                if self._animate_gif_frames:
                    self._animate_gif_idx = 0
                    display.animate_gif_next_frame(self)
                else:
                    self._current_photo_ref = display.display_static_image(self.canvas, adjusted_image)
            else:
                self._current_photo_ref = display.display_static_image(self.canvas, adjusted_image)

            hud.update_hud(self)
            if self.info_displayed:
                self.display_image_info()

        except (FileNotFoundError, IOError, tk.TclError) as e:
            logger.error(f"Error displaying image '{image_path.name}': {e}", exc_info=True)
            self.next_image_auto()
            return

        try:
            self.preloaded_images = image_loader.preload_images(
                self.images, self.current_index, self.preloaded_images, self.loop
            )
        except ImageNotFound as e:
            logger.warning(f"Failed to preload image, it may have been moved or deleted: {e}")

        if self.timer_running and not self._gif_animation_after_id:
            self.after_id = self.window.after(int(self.delay * 1000), self.next_image_auto)

    def next_image_auto(self) -> None:
        """
        Automatically advance to the next image as part of the slideshow timer.

        This method is called by the `after` loop when the slideshow is running.
        It stops if looping is disabled and the end of the list is reached.
        """
        if not self.loop and self.current_index >= len(self.images) - 1:
            self.timer_running = False
            hud.update_hud(self)
            return
        self.show_image(self.current_index + 1)

    def next_image(self) -> None:
        """Manually advance to the next image, stopping the timer."""
        self.timer_running = False
        self.show_image(self.current_index + 1)

    def previous_image(self) -> None:
        """Manually go to the previous image, stopping the timer."""
        self.timer_running = False
        self.show_image(self.current_index - 1)

    def jump_forward_ten(self) -> None:
        """Jump 10 images forward, stopping the timer."""
        self.timer_running = False
        self.show_image(self.current_index + 10)

    def jump_backward_ten(self) -> None:
        """Jump 10 images backward, stopping the timer."""
        self.timer_running = False
        self.show_image(self.current_index - 10)

    def toggle_timer(self) -> None:
        """Toggle the automatic slideshow timer on or off."""
        self.timer_running = not self.timer_running
        if self.timer_running:
            self.after_id = self.window.after(int(self.delay * 1000), self.next_image_auto)
        else:
            if self.after_id:
                self.window.after_cancel(self.after_id)
                self.after_id = None
        hud.update_hud(self)

    def toggle_auto_stop(self) -> None:
        """Toggle the auto-stop feature on or off."""
        self.auto_stop = not self.auto_stop
        if self.auto_stop:
            self.stop_time = time.time() + self.auto_stop_delay
            logger.info(f"Auto-stop enabled. Slideshow will stop in {self.auto_stop_delay} seconds.")
        else:
            self.stop_time = 0.0
            logger.info("Auto-stop disabled.")
        hud.update_hud(self)

    def shuffle_images(self) -> None:
        """Shuffle the order of images and display the new current one."""
        self.images, self.current_index = image_loader.shuffle_images(self.images, self.current_index)
        self.show_image(self.current_index)

    def sort_images(self) -> None:
        """Sort images by modification time and display the first one."""
        try:
            self.images = image_loader.sort_images_by_time(self.images)
        except ImageNotFound as e:
            logger.error(f"Failed to sort images because a file was not found: {e}")
            messagebox.showerror("Error", f"Could not sort images.\nFile not found: {e}")
            return
        self.current_index = 0
        self.show_image(self.current_index)

    def toggle_favorite(self) -> None:
        """Toggle the favorite status of the current image."""
        self.favorites = favorites.toggle_favorite(self.current_index, self.favorites)
        hud.update_hud(self)

    def yoink_image(self) -> None:
        """Copy the current image to the 'yoink' directory."""
        if self.images:
            yoink.send_to_yoink(self.images[self.current_index], self.canvas)

    def toggle_image_info(self) -> None:
        """Toggle the display of the image information overlay."""
        self.info_displayed = not self.info_displayed
        if self.info_displayed:
            self.display_image_info()
        else:
            self.clear_image_info()
        hud.update_hud(self)

    def display_image_info(self) -> None:
        """Display an overlay with information about the current image."""
        self.clear_image_info()
        if not self.images:
            return
        image_path = self.images[self.current_index]

        info_text = f"{image_path.name}\n"
        if self._current_photo_ref:
            info_text += f"{self._current_photo_ref.width()}x{self._current_photo_ref.height()} (display)\n"

        exif_str = exif_utils.get_formatted_exif_data(image_path)
        if exif_str:
            info_text += f"\n{exif_str}"

        self.canvas.create_text(
            10,
            10,
            text=info_text,
            fill="white",
            font=("Helvetica", 10),
            anchor="nw",
            tags="info_text",
        )

    def clear_image_info(self) -> None:
        """Clear the image information overlay from the canvas."""
        self.canvas.delete("info_text")

    def on_resize(self, event: tk.Event) -> None:
        """
        Handle the window resize event.

        To avoid excessive updates during resizing, it schedules the image
        to be re-rendered after a short delay once resizing has stopped.

        Args:
            event: The Tkinter event object.
        """
        if event.widget == self.window:
            if self._resize_job:
                self.window.after_cancel(self._resize_job)
            if event.width > 50 and event.height > 50:
                self._resize_job = self.window.after(
                    250, lambda: self.show_image(self.current_index, force_reload=False)
                )

    def quit(self) -> None:
        """Cleanly shut down the application."""
        logger.info("Quit command received. Saving favorites and closing.")
        favorites.save_favorites(self.image_folder, self.favorites, len(self.images))
        if self.after_id:
            self.window.after_cancel(self.after_id)
        if self._gif_animation_after_id:
            self.window.after_cancel(self._gif_animation_after_id)
        self.window.destroy()

    def run(self) -> None:
        """Start the Tkinter main loop."""
        self.window.mainloop()
