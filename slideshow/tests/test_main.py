# -*- coding: utf-8 -*-
"""
Unit tests for the __main__ module of the slideshow application.

This module ensures that running the package as a script (`python -m slideshow`)
correctly delegates to the main CLI function.
"""

import runpy
from unittest.mock import patch

def test_main_entry_point(mocker):
    """
    Test that running the package as a script calls the cli.main function.
    
    This test uses runpy to execute the slideshow.__main__ module, which
    is the correct way to test an `if __name__ == '__main__'` block.
    """
    # Patch the target function
    mock_cli_main = mocker.patch('slideshow.cli.main')
    
    # Run the module by name
    runpy.run_module('slideshow.__main__', run_name='__main__')
    
    # Assert that the mocked function was called
    mock_cli_main.assert_called_once()
