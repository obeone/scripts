"""
Manages the "favorites" functionality for the slideshow.

This module handles loading, saving, and modifying the list of favorite images.
Favorites are stored as a list of indices corresponding to the main image list
in a text file within the image directory.
"""

import logging
from pathlib import Path
from typing import List

from .config import FAVORITES_FILENAME

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def load_favorites(image_folder: Path, num_images: int) -> List[int]:
    """
    Loads favorite image indices from the favorites file in the image folder.

    It reads integer indices from the file, validates them against the total
    number of images, and returns a sorted list of valid favorite indices.

    Args:
        image_folder (Path): The directory where images are located and where
                             the favorites file is expected to be.
        num_images (int): The total number of images currently loaded in the
                          slideshow, used for validation.

    Returns:
        List[int]: A sorted list of valid favorite indices. Returns an empty
                   list if the file doesn't exist or contains no valid indices.
    """
    favorites_file = image_folder / FAVORITES_FILENAME
    if not favorites_file.exists() or num_images == 0:
        if not favorites_file.exists():
            logger.debug(f"Favorites file not found: {favorites_file}. No favorites to load.")
        else:
            logger.info("Favorites not loaded: Image list is currently empty.")
        return []

    try:
        with open(favorites_file, 'r', encoding='utf-8') as f:
            # Read indices, ensuring they are digits and stripping whitespace
            loaded_indices = [int(line.strip()) for line in f if line.strip().isdigit()]
            # Filter to keep only valid indices within the current image list bounds
            valid_favorites = [idx for idx in loaded_indices if 0 <= idx < num_images]
        logger.info(f"Loaded {len(valid_favorites)} valid favorite indices from {favorites_file}.")
        return sorted(valid_favorites)
    except ValueError:
        logger.error(f"Error parsing favorite indices from '{favorites_file}'. File might be corrupt.")
    except Exception as e:
        logger.error(f"Error loading favorites from '{favorites_file}': {e}")
    
    return []

def save_favorites(image_folder: Path, favorites: List[int], num_images: int) -> None:
    """
    Saves the current list of favorite image indices to the favorites file.

    Before saving, it ensures all indices in the list are valid and unique.

    Args:
        image_folder (Path): The directory where the favorites file will be saved.
        favorites (List[int]): The list of favorite indices to save.
        num_images (int): The total number of images, for validation.
    """
    if not image_folder.exists():
        try:
            image_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created image folder at {image_folder} for saving favorites.")
        except OSError as e:
            logger.error(f"Cannot save favorites: Image folder '{image_folder}' does not exist and could not be created. Error: {e}")
            return

    favorites_file = image_folder / FAVORITES_FILENAME
    try:
        # Filter out invalid indices before saving
        valid_favorites = [idx for idx in favorites if 0 <= idx < num_images]
        with open(favorites_file, 'w', encoding='utf-8') as f:
            # Ensure uniqueness and sort before writing
            for index in sorted(list(set(valid_favorites))):
                f.write(f"{index}\n")
        logger.info(f"Saved {len(valid_favorites)} favorite indices to {favorites_file}.")
    except Exception as e:
        logger.error(f"Error saving favorites to '{favorites_file}': {e}")

def toggle_favorite(current_index: int, favorites: List[int]) -> List[int]:
    """
    Toggles the favorite status of an image index.

    If the index is already in the favorites list, it's removed. Otherwise,
    it's added. The list is kept sorted.

    Args:
        current_index (int): The index of the image to toggle.
        favorites (List[int]): The current list of favorite indices.

    Returns:
        List[int]: The modified (or unmodified) list of favorite indices.
    """
    if current_index in favorites:
        favorites.remove(current_index)
        logger.info(f"Image index {current_index} removed from favorites.")
    else:
        favorites.append(current_index)
        logger.info(f"Image index {current_index} added to favorites.")
    
    return sorted(favorites)
