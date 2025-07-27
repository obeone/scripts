"""
EXIF Data Extraction and Formatting Utilities.

This module provides functions to extract, interpret, and format EXIF (Exchangeable
Image File Format) data from image files. It uses the Pillow library to access
the metadata embedded in images by digital cameras.
"""

import logging
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
import datetime

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def get_formatted_exif_data(image_path: Path) -> str:
    """
    Extracts and formats key EXIF data from an image file.

    Args:
        image_path (Path): The path to the image file.

    Returns:
        str: A formatted, multi-line string containing key EXIF information,
             or an empty string if no EXIF data is found or an error occurs.
    """
    if not image_path.exists():
        logger.warning(f"Cannot get EXIF data: file not found at {image_path}")
        return "File not found."

    try:
        with Image.open(image_path) as img:
            # The `getexif()` method returns a dictionary of EXIF data.
            exif_data = img.getexif()
            if not exif_data:
                logger.debug(f"No EXIF data found for image: {image_path.name}")
                return ""

            exif_info = {}
            # Iterate through the EXIF data and map tag IDs to human-readable names
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)
                exif_info[tag_name] = value

            # Format the extracted data into a readable string
            formatted_lines = []
            
            # Camera model
            if 'Model' in exif_info:
                formatted_lines.append(f"Camera: {exif_info['Model']}")
            
            # Lens model (often requires checking specific MakerNote tags, simplified here)
            if 'LensModel' in exif_info:
                 formatted_lines.append(f"Lens: {exif_info['LensModel']}")

            # Exposure settings
            exposure_time = exif_info.get('ExposureTime')
            f_number = exif_info.get('FNumber')
            iso_speed = exif_info.get('ISOSpeedRatings')
            
            exposure_str = ""
            if exposure_time:
                exposure_str += f"1/{int(1/exposure_time)}s" if exposure_time < 1 else f"{exposure_time}s"
            if f_number:
                exposure_str += f"  f/{f_number}"
            if iso_speed:
                exposure_str += f"  ISO {iso_speed}"
            if exposure_str:
                formatted_lines.append(f"Exposure: {exposure_str.strip()}")

            # Date and time
            date_time = exif_info.get('DateTimeOriginal') or exif_info.get('DateTime')
            if date_time:
                try:
                    # Attempt to parse the date string into a more friendly format
                    dt_obj = datetime.datetime.strptime(date_time, '%Y:%m:%d %H:%M:%S')
                    formatted_lines.append(f"Date: {dt_obj.strftime('%Y-%m-%d %H:%M:%S')}")
                except (ValueError, TypeError):
                    formatted_lines.append(f"Date: {date_time}") # Fallback to raw string

            return "\n".join(formatted_lines)

    except Exception as e:
        logger.error(f"Error reading EXIF data for '{image_path.name}': {e}")
        return "Could not read EXIF data."
