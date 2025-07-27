# -*- coding: utf-8 -*-
"""
Unit tests for the main application class, ImageSlideshowApp.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from PIL import Image

from slideshow import app, display, hud, image_loader
from slideshow.app import ImageSlideshowApp

# --- Fixtures ---

@pytest.fixture
def mock_app_dependencies(mocker):
    """Mocks all external dependencies for ImageSlideshowApp."""
    mocker.patch('slideshow.app.image_loader.load_images_from_folder', return_value=[Path("img1.png"), Path("img2.png")])
    mocker.patch('slideshow.app.favorites.load_favorites', return_value=[])
    mocker.patch('slideshow.app.controls.bind_controls')
    mocker.patch('slideshow.app.hud.update_hud')
    mocker.patch('slideshow.app.display.resize_image', return_value=Image.new('RGB', (10, 10)))
    mocker.patch('slideshow.app.display.adjust_brightness', return_value=Image.new('RGB', (10, 10)))
    mocker.patch('slideshow.app.display.display_static_image')
    mocker.patch('slideshow.app.image_loader.preload_images', return_value={})
    mocker.patch('PIL.Image.open', return_value=Image.new('RGB', (100, 100)))

@pytest.fixture
def app_instance(mock_app_dependencies, patch_tk):
    """Provides a mocked instance of ImageSlideshowApp for testing."""
    window = patch_tk['Tk']()
    # Mock methods that would otherwise be called during __init__ via setup()
    with patch.object(ImageSlideshowApp, 'show_image') as mock_show_image:
        app = ImageSlideshowApp(window, "/fake/dir", delay=2.0, auto_stop_delay=None)
        mock_show_image.assert_called_once_with(0)
    
    # Set some required attributes that are normally set by Tkinter
    app.canvas.winfo_width.return_value = 800
    app.canvas.winfo_height.return_value = 600
    
    return app

# --- Tests for __init__ ---

def test_app_init_success(app_instance):
    """Test successful initialization of the application."""
    assert app_instance.delay == 2.0
    assert not app_instance.auto_stop
    assert len(app_instance.images) == 2
    app_instance.window.title.assert_called_with("Image Slideshow")
    app_instance.window.attributes.assert_called_with('-fullscreen', True)

@patch('slideshow.app.image_loader.load_images_from_folder', return_value=[])
@patch('slideshow.app.messagebox.showerror')
def test_app_init_no_images(mock_showerror, mock_load_images, patch_tk):
    """Test initialization when no images are found."""
    window = patch_tk['Tk']()
    app = ImageSlideshowApp(window, "/fake/dir", 2.0, None)
    
    mock_showerror.assert_called_once()
    window.after.assert_called_once_with(50, window.destroy)

# --- Tests for show_image ---

def test_show_image_flow(app_instance):
    """Test the main logic of the show_image method."""
    app_instance.timer_running = True
    app_instance.after_id = "some_id" # Simulate an existing timer

    app_instance.show_image(1)

    # Check state
    assert app_instance.current_index == 1
    
    # Check mocks
    app_instance.window.after_cancel.assert_called_once_with("some_id")
    Image.open.assert_called_once_with(app_instance.images[1])
    display.resize_image.assert_called_once()
    display.adjust_brightness.assert_called_once()
    display.display_static_image.assert_called_once()
    hud.update_hud.assert_called_once_with(app_instance)
    image_loader.preload_images.assert_called_once()
    
    # Check that a new timer was set
    app_instance.window.after.assert_called_with(int(app_instance.delay * 1000), app_instance.next_image_auto)

def test_show_image_uses_cache(app_instance):
    """Test that show_image uses a preloaded image from the cache."""
    cached_image = Image.new('RGB', (50, 50), color='red')
    app_instance.preloaded_images[0] = cached_image
    
    with patch('PIL.Image.open') as mock_open:
        app_instance.show_image(0)
        mock_open.assert_not_called() # Should not open from disk

    # Check that the cached image was used for resizing
    display.resize_image.assert_called_once_with(cached_image, 800, 600)

# --- Tests for next_image_auto ---

def test_next_image_auto_loops(app_instance):
    """Test that next_image_auto calls show_image with the next index."""
    app_instance.current_index = 0
    with patch.object(app_instance, 'show_image') as mock_show_image:
        app_instance.next_image_auto()
        mock_show_image.assert_called_once_with(1)

def test_next_image_auto_no_loop_end(app_instance):
    """Test that next_image_auto stops at the end if looping is off."""
    app_instance.loop = False
    app_instance.current_index = len(app_instance.images) - 1 # Last image
    
    with patch.object(app_instance, 'show_image') as mock_show_image:
        app_instance.next_image_auto()
        
        # Should not advance
        mock_show_image.assert_not_called()
        # Timer should be stopped
        assert not app_instance.timer_running
        # HUD should be updated to reflect paused state
        hud.update_hud.assert_called_with(app_instance)
