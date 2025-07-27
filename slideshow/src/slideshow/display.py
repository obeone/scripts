"""
Image Display and Manipulation Module.

This module handles tasks related to rendering images on the Tkinter canvas,
including resizing, brightness adjustment, handling static images and animated GIFs,
and robustly creating PhotoImage objects.
"""

import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance, ImageSequence
import logging
import io
import base64
import tempfile
import os
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .app import ImageSlideshowApp

logger = logging.getLogger(__name__)

def resize_image(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """
    Resizes a PIL Image to fit within target dimensions while maintaining aspect ratio.

    Args:
        image (Image.Image): The original PIL Image object.
        target_width (int): The maximum width for the resized image.
        target_height (int): The maximum height for the resized image.

    Returns:
        Image.Image: The resized PIL Image. Returns a copy if resizing fails.
    """
    if target_width <= 0 or target_height <= 0:
        logger.warning(f"Resize_image: Invalid target dimensions ({target_width}x{target_height}).")
        return image.copy()

    original_width, original_height = image.width, image.height
    if original_width == 0 or original_height == 0:
        logger.warning(f"Resize_image: Invalid original image dimensions ({original_width}x{original_height}).")
        return image.copy()

    image_aspect_ratio = original_width / original_height
    target_aspect_ratio = target_width / target_height

    new_width, new_height = target_width, target_height
    if image_aspect_ratio > target_aspect_ratio:
        new_height = int(new_width / image_aspect_ratio)
    else:
        new_width = int(new_height * image_aspect_ratio)

    new_width = max(1, new_width)
    new_height = max(1, new_height)

    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = 1  # Fallback for older Pillow versions

    try:
        return image.resize((new_width, new_height), resample_filter)
    except Exception as e:
        logger.error(f"Error during image resize: {e}")
        return image.copy()

def adjust_brightness(image: Image.Image, brightness_factor: float) -> Image.Image:
    """
    Adjusts the brightness of a PIL Image.

    Args:
        image (Image.Image): The PIL Image to adjust.
        brightness_factor (float): The enhancement factor. 1.0 is original brightness.

    Returns:
        Image.Image: The brightness-adjusted PIL Image.
    """
    if brightness_factor == 1.0:
        return image

    try:
        enhancer = ImageEnhance.Brightness(image)
        return enhancer.enhance(brightness_factor)
    except Exception as e:
        logger.warning(f"Could not adjust brightness for image (mode {image.mode}): {e}")
        return image

def create_photoimage_robust(image: Image.Image) -> tk.PhotoImage | None:
    """
    Creates a tk.PhotoImage from a PIL Image with comprehensive error handling.

    This function employs multiple strategies to handle problematic images:
    1. Validates image dimensions and mode
    2. Converts to RGBA if needed
    3. "Cleans" the image by re-encoding to remove problematic metadata
    4. Uses multiple fallback methods if direct conversion fails

    Args:
        image (Image.Image): The PIL Image to convert.

    Returns:
        tk.PhotoImage | None: The created PhotoImage, or None if all methods fail.
    """
    # Validate image dimensions
    if image.width <= 0 or image.height <= 0:
        logger.error(f"Invalid image dimensions: {image.width}x{image.height}")
        return None

    # Step 1: Aggressively convert to RGB mode for maximum Tkinter compatibility
    # RGB is the most reliable mode for ImageTk.PhotoImage
    if image.mode != 'RGB':
        logger.debug(f"Converting image from mode '{image.mode}' to 'RGB' for maximum Tkinter compatibility.")
        # Handle transparency by adding a white background
        if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
            # Create white background for transparent images
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        else:
            image = image.convert('RGB')

    # Step 2: "Clean" the image by re-encoding it to remove problematic metadata
    try:
        with io.BytesIO() as clean_buffer:
            image.save(clean_buffer, format='JPEG', quality=95)  # JPEG is more reliable than PNG
            clean_buffer.seek(0)
            image = Image.open(clean_buffer).copy()  # This removes problematic metadata
            logger.debug("Image cleaned by re-encoding to JPEG to remove metadata issues.")
    except Exception as clean_error:
        logger.debug(f"Image cleaning failed, using original: {clean_error}")
        # Continue with original image if cleaning fails

    # Step 3: Try direct ImageTk conversion with cleaned RGB image
    try:
        photo = cast(tk.PhotoImage, ImageTk.PhotoImage(image))
        return photo
    except Exception as e1:
        logger.warning(f"ImageTk.PhotoImage failed: {e1}. Trying BytesIO fallback.")
        
        # Fallback 1: In-memory PNG conversion with base64 encoding
        try:
            with io.BytesIO() as bio:
                image.save(bio, format='PNG')
                bio.seek(0)
                return tk.PhotoImage(data=base64.b64encode(bio.getvalue()))
        except Exception as e2:
            logger.warning(f"BytesIO fallback failed: {e2}. Trying temp file fallback.")
            
            # Fallback 2: Temporary file conversion
            try:
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                    temp_path = tmp_file.name
                image.save(temp_path, 'PNG')
                photo = tk.PhotoImage(file=temp_path)
                os.unlink(temp_path)  # Clean up the temporary file
                return photo
            except Exception as e3:
                logger.error(f"All PhotoImage creation methods failed. Last error: {e3}")
                return None

def display_static_image(canvas: tk.Canvas, image: Image.Image) -> tk.PhotoImage | None:
    """
    Displays a static PIL image on the canvas.

    Args:
        canvas (tk.Canvas): The canvas to draw on.
        image (Image.Image): The (already resized and adjusted) PIL image.

    Returns:
        tk.PhotoImage | None: The reference to the created PhotoImage to prevent
                              garbage collection, or None on failure.
    """
    photo = create_photoimage_robust(image)
    if photo:
        canvas.delete("image")
        canvas.create_image(
            canvas.winfo_width() // 2, canvas.winfo_height() // 2,
            image=photo, anchor=tk.CENTER, tags="image"
        )
    else:
        logger.error("Failed to create PhotoImage for static display.")
        canvas.delete("all")
        canvas.create_text(
            canvas.winfo_width() // 2, canvas.winfo_height() // 2,
            text="Error displaying image", fill="red", font=("Helvetica", 16)
        )
    return photo

def animate_gif_next_frame(app: 'ImageSlideshowApp') -> None:
    """
    Displays the next frame of an animated GIF and schedules the subsequent frame.

    Args:
        app (ImageSlideshowApp): The main application instance containing the state
                                 for GIF animation.
    """
    if not app._animate_gif_frames or app._animate_gif_idx >= len(app._animate_gif_frames):
        return

    frame_photo = app._animate_gif_frames[app._animate_gif_idx]
    duration_ms = app._animate_gif_durations[app._animate_gif_idx]

    app.canvas.delete("image")
    app.canvas.create_image(
        app.canvas.winfo_width() // 2, app.canvas.winfo_height() // 2,
        image=frame_photo, anchor=tk.CENTER, tags="image"
    )
    app._current_photo_ref = frame_photo

    app._animate_gif_idx = (app._animate_gif_idx + 1) % len(app._animate_gif_frames)

    if app.timer_running and app._animate_gif_idx == 0:
        app.after_id = app.window.after(int(app.delay * 1000), app.next_image_auto)
    else:
        app._gif_animation_after_id = app.window.after(duration_ms, lambda: animate_gif_next_frame(app))
