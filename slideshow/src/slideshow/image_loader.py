"""
Image Loading, Caching, and Management Module.

This module is responsible for discovering image files in a directory,
managing the list of images (sorting, shuffling), and handling the
preloading cache for a smooth user experience.
"""

import logging
import random
from pathlib import Path
from typing import List, Dict, Tuple
from PIL import Image

from .config import SUPPORTED_IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

def load_images_from_folder(image_folder: Path) -> List[Path]:
    """
    Scans a directory recursively for supported image files.

    Args:
        image_folder (Path): The directory to scan.

    Returns:
        List[Path]: A sorted list of Path objects for all valid images found.
                    Returns an empty list if the folder doesn't exist or no
                    images are found.
    """
    if not image_folder.is_dir():
        logger.error(f"The specified image folder '{image_folder}' does not exist or is not a directory.")
        return []

    logger.info(f"Scanning for images in: {image_folder}")
    
    raw_image_list = [
        item for item in image_folder.rglob('*')
        if item.is_file() and \
           item.name.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS) and \
           not item.name.startswith('.')
    ]

    if not raw_image_list:
        logger.warning(f"No images found in '{image_folder}' with supported extensions.")
        return []

    # Initial sort is by full path, which is deterministic
    sorted_images = sorted(raw_image_list)
    logger.info(f"Found {len(sorted_images)} images.")
    return sorted_images

def shuffle_images(images: List[Path], current_index: int) -> Tuple[List[Path], int]:
    """
    Shuffles the list of images in place, keeping the current image at the start.

    Args:
        images (List[Path]): The list of image paths to shuffle.
        current_index (int): The index of the currently displayed image.

    Returns:
        Tuple[List[Path], int]: A tuple containing the shuffled list of images
                                and the new index of the current image (which is 0).
    """
    if not images:
        return [], 0
    
    current_image = images[current_index]
    # Remove the current image to shuffle the rest
    other_images = images[:current_index] + images[current_index+1:]
    random.shuffle(other_images)
    
    # Create the new list with the current image at the front
    new_images = [current_image] + other_images
    logger.info(f"Shuffled {len(new_images)} images. Current image '{current_image.name}' is now at index 0.")
    return new_images, 0

def sort_images_by_time(images: List[Path], ascending: bool = True) -> List[Path]:
    """
    Sorts the list of images by their file modification time.

    Args:
        images (List[Path]): The list of image paths to sort.
        ascending (bool): True to sort from oldest to newest, False for newest to oldest.

    Returns:
        List[Path]: The sorted list of image paths.
    """
    if not images:
        return []

    try:
        # Sort by 'st_mtime' (time of last modification)
        sorted_list = sorted(images, key=lambda p: p.stat().st_mtime, reverse=not ascending)
        sort_order = "ascending (oldest first)" if ascending else "descending (newest first)"
        logger.info(f"Sorted {len(images)} images by modification time: {sort_order}.")
        return sorted_list
    except FileNotFoundError as e:
        logger.error(f"Error sorting images: file not found during stat call. {e}")
        # Return the list as is, or an empty list if the error is critical
        return images

def preload_images(
    images: List[Path], 
    current_index: int, 
    cache: Dict[int, Image.Image],
    loop: bool,
    count: int = 5
) -> Dict[int, Image.Image]:
    """
    Preloads subsequent images into a cache for faster display.

    Args:
        images (List[Path]): The full list of image paths.
        current_index (int): The index of the currently displayed image.
        cache (Dict[int, Image.Image]): The dictionary used for caching.
        loop (bool): Whether the slideshow is in loop mode.
        count (int): The number of images to preload.

    Returns:
        Dict[int, Image.Image]: The updated cache dictionary.
    """
    if not images:
        return {}

    # Determine which indices to preload
    indices_to_preload = []
    for i in range(1, count + 1):
        next_idx = (current_index + i) % len(images)
        if next_idx not in cache:
            indices_to_preload.append(next_idx)
        if not loop and (current_index + i) >= (len(images) - 1):
            break
    
    # Load the identified images
    for index_to_load in indices_to_preload:
        image_path = images[index_to_load]
        try:
            image = Image.open(image_path)
            image.load()  # Force loading image data into memory
            
            # Convert to RGB immediately during preloading for maximum compatibility
            if image.mode != 'RGB':
                logger.debug(f"Converting preloaded image from mode '{image.mode}' to 'RGB' for maximum compatibility.")
                # Handle transparency by adding a white background
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                    image = background
                else:
                    image = image.convert('RGB')
            
            cache[index_to_load] = image
            logger.debug(f"Preloaded image {index_to_load + 1}/{len(images)}: {image_path.name}")
        except Exception as e:
            logger.error(f"Error preloading image '{image_path.name}': {e}")
            if index_to_load in cache:
                del cache[index_to_load]

    # Eviction strategy: remove images far from the current one
    keys_to_keep = set()
    preload_window_size = count * 2
    for i in range(-preload_window_size, preload_window_size + 1):
        idx_to_keep = (current_index + i + len(images)) % len(images)
        keys_to_keep.add(idx_to_keep)

    current_cache_keys = list(cache.keys())
    for key in current_cache_keys:
        if key not in keys_to_keep:
            del cache[key]
            
    return cache
