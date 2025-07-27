#!/usr/bin/env python3
"""
Main entry point for the slideshow application.

This script serves as the executable entry point when the package is run as a
module using `python -m slideshow`. It simply imports and calls the main
function from the `cli` module.
"""

from .cli import main

if __name__ == "__main__":
    main()
