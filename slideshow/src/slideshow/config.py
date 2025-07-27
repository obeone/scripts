"""
Configuration constants for the Image Slideshow application.

This module centralizes settings like supported file types, default values,
and other configuration parameters to make them easily accessible and modifiable
across the application.
"""

# A tuple of supported image file extensions (case-insensitive).
# These are the formats that the application will attempt to load and display.
SUPPORTED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')

# Default delay in seconds between image transitions in automatic playback mode.
DEFAULT_DELAY = 3.0

# Default duration in seconds after which the slideshow automatically stops.
# A value of 3600 corresponds to one hour.
DEFAULT_AUTO_STOP_DELAY = 3600

# Default logging level for the application.
# Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'.
DEFAULT_LOG_LEVEL = 'INFO'

# Name of the file used to store the list of favorite images.
# This file is created in the root of the scanned image folder.
FAVORITES_FILENAME = 'favorites.txt'
