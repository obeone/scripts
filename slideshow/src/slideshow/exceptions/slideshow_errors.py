"""
Domain-specific errors for the Slideshow application.

This module defines a hierarchy of custom exceptions that are specific to the
slideshow's domain logic. Using these exceptions allows for more precise error
handling than relying on generic built-in exceptions.
"""

class SlideshowError(Exception):
    """Base class for all slideshow domain errors.

    This exception should not be raised directly. Instead, subclass it to create
    more specific error types.
    """

class ImageNotFound(SlideshowError):
    """Raised when an expected image file is missing."""


class CacheMiss(SlideshowError):
    """Raised when a requested item is not found in cache."""
