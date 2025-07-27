# -*- coding: utf-8 -*-
"""
Unit tests for the display module.

This module tests image manipulation functions like resizing and robust
PhotoImage creation.
"""

import pytest
from PIL import Image
from unittest.mock import patch, MagicMock

from slideshow import display

# --- Fixtures ---

@pytest.fixture
def sample_image():
    """Provides a sample PIL Image for testing."""
    return Image.new('RGB', (200, 100), color='blue')

# --- Tests for resize_image ---

def test_resize_image_width_limited(sample_image):
    """Test resizing where width is the limiting factor."""
    resized = display.resize_image(sample_image, 100, 100)
    assert resized.size == (100, 50)

def test_resize_image_height_limited(sample_image):
    """Test resizing where height is the limiting factor."""
    resized = display.resize_image(sample_image, 300, 40)
    assert resized.size == (80, 40)

def test_resize_image_no_change_needed(sample_image):
    """Test resizing when the image is smaller than the target."""
    resized = display.resize_image(sample_image, 400, 200)
    # The current implementation will resize to fit, so it will be 400x200
    assert resized.size == (400, 200)

def test_resize_image_invalid_target_dims(sample_image, caplog):
    """Test that invalid target dimensions are handled gracefully."""
    resized = display.resize_image(sample_image, 0, -10)
    assert resized.size == sample_image.size
    assert "Invalid target dimensions" in caplog.text

def test_resize_image_invalid_source_dims(caplog):
    """Test that invalid source image dimensions are handled."""
    invalid_image = Image.new('RGB', (0, 0))
    resized = display.resize_image(invalid_image, 100, 100)
    assert resized.size == invalid_image.size
    assert "Invalid original image dimensions" in caplog.text

# --- Tests for create_photoimage_robust ---

@patch('slideshow.display.ImageTk.PhotoImage')
def test_create_photoimage_robust_success_primary(mock_photoimage, sample_image):
    """Test successful creation using the primary ImageTk method."""
    mock_instance = MagicMock()
    mock_photoimage.return_value = mock_instance
    
    result = display.create_photoimage_robust(sample_image)
    
    mock_photoimage.assert_called_once_with(sample_image)
    assert result == mock_instance

@patch('slideshow.display.tk.PhotoImage')
@patch('slideshow.display.ImageTk.PhotoImage', side_effect=Exception("Primary failed"))
def test_create_photoimage_robust_fallback_bytesio(mock_imagetk_pi, mock_tk_pi, sample_image, caplog):
    """Test successful creation using the BytesIO fallback."""
    mock_instance = MagicMock()
    mock_tk_pi.return_value = mock_instance
    
    result = display.create_photoimage_robust(sample_image)
    
    assert "Trying BytesIO fallback" in caplog.text
    mock_tk_pi.assert_called_once()
    assert result == mock_instance

@patch('os.unlink')
@patch('tempfile.NamedTemporaryFile')
@patch('slideshow.display.tk.PhotoImage')
@patch('slideshow.display.ImageTk.PhotoImage', side_effect=Exception("Primary failed"))
def test_create_photoimage_robust_fallback_tempfile(mock_imagetk_pi, mock_tk_pi, mock_tempfile, mock_unlink, sample_image, caplog):
    """Test successful creation using the temp file fallback."""
    # Mock the context manager for NamedTemporaryFile
    mock_file_handle = MagicMock()
    mock_file_handle.name = "/tmp/fake_temp_file.png"
    mock_tempfile.return_value.__enter__.return_value = mock_file_handle

    # Mock the final PhotoImage creation
    mock_instance = MagicMock()
    mock_tk_pi.side_effect = [Exception("BytesIO failed"), mock_instance]

    result = display.create_photoimage_robust(sample_image)

    assert "Trying temp file fallback" in caplog.text
    mock_tempfile.assert_called_once_with(suffix='.png', delete=False)
    mock_unlink.assert_called_once_with("/tmp/fake_temp_file.png")
    assert result == mock_instance

@patch('slideshow.display.ImageTk.PhotoImage', side_effect=Exception("Primary failed"))
@patch('slideshow.display.tk.PhotoImage', side_effect=Exception("All fallbacks failed"))
def test_create_photoimage_robust_all_fail(mock_tk_pi, mock_imagetk_pi, sample_image, caplog):
    """Test that None is returned when all creation methods fail."""
    result = display.create_photoimage_robust(sample_image)
    
    assert result is None
    assert "All PhotoImage creation methods failed" in caplog.text
