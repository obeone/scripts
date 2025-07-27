# -*- coding: utf-8 -*-
"""
Configuration and fixtures for pytest.

This module defines shared fixtures used across the test suite for the slideshow application.
Fixtures include temporary directories for images, mocking of GUI components (Tkinter),
and logging setup.
"""

import logging
import sys
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

@pytest.fixture
def tmp_image_dir(tmp_path: Path) -> Iterator[Path]:
    """
    Create a temporary directory and populate it with a dummy image file.

    This fixture creates a temporary directory and a 'data' subdirectory within it.
    It then generates a small dummy PNG image and saves it as 'test_image.png'
    in the 'data' directory.

    Args:
        tmp_path (Path): The pytest fixture for creating temporary directories.

    Yields:
        Path: The path to the 'data' subdirectory containing the test image.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    image_path = data_dir / "test_image.png"
    
    # Create a small, simple dummy image
    dummy_image = Image.new('RGB', (100, 100), color = 'red')
    dummy_image.save(image_path, 'PNG')
    
    yield data_dir

@pytest.fixture
def patch_tk(mocker):
    """
    Patch the Tkinter module to avoid GUI instantiation during tests.

    This fixture patches 'tkinter.Tk' and 'tkinter.Canvas' to be MagicMock objects.
    This prevents actual windows from being created, which is essential for running
    tests in a headless environment.

    Args:
        mocker: The pytest-mock fixture.

    Returns:
        dict: A dictionary containing the mocked 'Tk' and 'Canvas' classes.
    """
    mock_tk = mocker.patch('tkinter.Tk', autospec=True)
    mock_canvas = mocker.patch('tkinter.Canvas', autospec=True)
    return {
        "Tk": mock_tk,
        "Canvas": mock_canvas,
    }

@pytest.fixture
def dummy_canvas(patch_tk):
    """
    Provide a dummy Tkinter Canvas instance.

    This fixture leverages 'patch_tk' to create a MagicMock instance of a Tkinter Canvas.
    It is configured with some default attributes like 'winfo_width' and 'winfo_height'
    to simulate a real canvas for geometry calculations.

    Args:
        patch_tk: The fixture that patches Tkinter.

    Returns:
        MagicMock: A mocked instance of a Tkinter Canvas.
    """
    canvas = patch_tk["Canvas"].return_value
    canvas.winfo_width.return_value = 800
    canvas.winfo_height.return_value = 600
    return canvas

@pytest.fixture
def caplog_info(caplog):
    """
    Set the logging level to INFO for the duration of a test.

    This fixture configures the root logger to capture messages at the INFO level
    and above. It's useful for tests that need to assert on log output.

    Args:
        caplog: The pytest fixture for capturing log output.

    Returns:
        LogCaptureFixture: The configured caplog fixture.
    """
    caplog.set_level(logging.INFO)
    return caplog
