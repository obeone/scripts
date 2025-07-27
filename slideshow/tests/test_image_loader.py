# -*- coding: utf-8 -*-
"""
Unit tests for the image_loader module.

This module tests the functionality of image discovery, sorting, and filtering.
"""

from pathlib import Path
import pytest

from slideshow.image_loader import load_images_from_folder

def test_load_images_from_folder_success(tmp_path: Path):
    """
    Test successful loading and sorting of images from a directory.
    """
    # Create a directory structure with images
    d = tmp_path / "images"
    d.mkdir()
    sub_dir = d / "sub"
    sub_dir.mkdir()

    # Create some dummy image files
    (d / "b_image.jpg").touch()
    (d / "a_image.png").touch()
    (sub_dir / "c_image.jpeg").touch()
    
    # Create non-image and hidden files that should be ignored
    (d / "document.txt").touch()
    (d / ".hidden_image.png").touch()

    # Run the function
    images = load_images_from_folder(d)

    # Assertions
    assert len(images) == 3
    # Check if the list is sorted by path
    assert images[0].name == "a_image.png"
    assert images[1].name == "b_image.jpg"
    assert images[2].name == "c_image.jpeg"

def test_load_images_from_non_existent_folder(caplog):
    """
    Test behavior when the specified folder does not exist.
    """
    non_existent_path = Path("/path/to/non_existent_folder")
    images = load_images_from_folder(non_existent_path)

    assert images == []
    assert f"The specified image folder '{non_existent_path}' does not exist" in caplog.text

def test_load_images_from_empty_folder(tmp_path: Path, caplog):
    """
    Test behavior when the folder is empty.
    """
    d = tmp_path / "empty_images"
    d.mkdir()
    
    images = load_images_from_folder(d)

    assert images == []
    assert f"No images found in '{d}'" in caplog.text

def test_load_images_from_folder_with_no_supported_files(tmp_path: Path, caplog):
    """
    Test behavior when the folder contains no supported image file types.
    """
    d = tmp_path / "other_files"
    d.mkdir()
    (d / "document.txt").touch()
    (d / "archive.zip").touch()

    images = load_images_from_folder(d)

    assert images == []
    assert f"No images found in '{d}'" in caplog.text
