# -*- coding: utf-8 -*-
"""
Unit tests for the command-line interface (CLI) of the slideshow application.

This module tests the argument parsing and application initialization logic
defined in `slideshow.cli`.
"""

import sys
from unittest.mock import patch, MagicMock

import pytest

from slideshow import cli

def test_main_basic_arguments(mocker, tmp_image_dir):
    """
    Test that the CLI correctly parses basic arguments and initializes the app.
    """
    # Mock dependencies
    mocker.patch('sys.argv', ['slideshow', str(tmp_image_dir), '--delay', '1.5'])
    mock_app_class = mocker.patch('slideshow.cli.ImageSlideshowApp', autospec=True)
    mock_app_instance = mock_app_class.return_value
    mock_app_instance.images = [MagicMock()]  # Simulate that images were loaded

    mocker.patch('tkinter.Tk')
    mocker.patch('coloredlogs.install')
    mocker.patch('logging.basicConfig')

    # Run the main function
    cli.main()

    # Assert that the app was initialized with the correct arguments
    mock_app_class.assert_called_once()
    _, kwargs = mock_app_class.call_args
    assert kwargs['image_folder'] == str(tmp_image_dir)
    assert kwargs['delay'] == 1.5
    
    # Assert that the app's run method was called
    mock_app_instance.run.assert_called_once()

def test_main_shuffle_argument(mocker, tmp_image_dir):
    """
    Test that the --shuffle argument correctly calls the shuffle_images method.
    """
    mocker.patch('sys.argv', ['slideshow', str(tmp_image_dir), '--shuffle'])
    mock_app_class = mocker.patch('slideshow.cli.ImageSlideshowApp', autospec=True)
    mock_app_instance = mock_app_class.return_value
    mock_app_instance.images = [MagicMock()]

    mocker.patch('tkinter.Tk')
    mocker.patch('coloredlogs.install')
    mocker.patch('logging.basicConfig')

    cli.main()

    mock_app_instance.shuffle_images.assert_called_once()

def test_main_sort_desc_argument(mocker, tmp_image_dir):
    """
    Test that the --sort-desc argument correctly sorts images.
    """
    mocker.patch('sys.argv', ['slideshow', str(tmp_image_dir), '--sort-desc'])
    mock_app_class = mocker.patch('slideshow.cli.ImageSlideshowApp', autospec=True)
    mock_app_instance = mock_app_class.return_value
    
    # Simulate images with stat results
    img1, img2 = MagicMock(), MagicMock()
    img1.stat.return_value.st_mtime = 100
    img2.stat.return_value.st_mtime = 200
    mock_app_instance.images = [img1, img2]

    mocker.patch('tkinter.Tk')
    mocker.patch('coloredlogs.install')
    mocker.patch('logging.basicConfig')

    cli.main()

    # Check that the images list was sorted in descending order of mtime
    assert mock_app_instance.images[0] == img2
    assert mock_app_instance.images[1] == img1
    mock_app_instance.show_image.assert_called_once_with(0)

def test_main_no_images_found(mocker, tmp_image_dir, caplog):
    """
    Test the CLI's behavior when the application finds no images.
    """
    mocker.patch('sys.argv', ['slideshow', str(tmp_image_dir)])
    mock_app_class = mocker.patch('slideshow.cli.ImageSlideshowApp', autospec=True)
    mock_app_instance = mock_app_class.return_value
    mock_app_instance.images = []  # Simulate no images loaded

    mocker.patch('tkinter.Tk')
    mocker.patch('coloredlogs.install')
    mocker.patch('logging.basicConfig')

    with pytest.raises(SystemExit) as e:
        cli.main()

    assert e.value.code == 1
    assert "Application startup failed, likely no images found." in caplog.text

def test_main_folder_not_found(mocker, caplog):
    """
    Test the CLI's error handling when the image folder does not exist.
    """
    non_existent_folder = "/path/to/non_existent_folder"
    mocker.patch('sys.argv', ['slideshow', non_existent_folder])
    
    # Mock the app class to raise FileNotFoundError
    mocker.patch('slideshow.cli.ImageSlideshowApp', side_effect=FileNotFoundError)
    mocker.patch('tkinter.Tk')
    mocker.patch('coloredlogs.install')
    mocker.patch('logging.basicConfig')

    with pytest.raises(SystemExit) as e:
        cli.main()

    assert e.value.code == 1
    assert f"The specified image folder does not exist: {non_existent_folder}" in caplog.text


def test_version_argument(mocker, capsys):
    """
    Test that the --version argument prints the version and exits.
    """
    mocker.patch('sys.argv', ['slideshow', '--version'])
    mocker.patch('importlib.metadata.version', return_value='0.1.0')

    with pytest.raises(SystemExit) as e:
        cli.main()

    captured = capsys.readouterr()
    assert "slideshow 0.1.0" in captured.out
    assert e.value.code == 0
