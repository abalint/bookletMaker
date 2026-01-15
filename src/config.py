"""
Centralized configuration and constants for the booklet maker.

This module contains all hardcoded values extracted from the original codebase,
making it easy to customize colors, sizes, and other settings in one place.
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Set


# Paper sizes in points (72 points per inch) - (width, height) in landscape
PAPER_SIZES: Dict[str, Tuple[float, float]] = {
    'tabloid': (17 * 72, 11 * 72),      # 11x17" (1224 x 792 pt)
    'a3': (1190, 842),                   # A3 (16.5" x 11.7")
    'letter': (11 * 72, 8.5 * 72),       # 8.5x11" (792 x 612 pt)
    'a4': (842, 595),                    # A4 (11.7" x 8.3")
    'legal': (14 * 72, 8.5 * 72),        # 8.5x14" (1008 x 612 pt)
}

DEFAULT_PAPER_SIZE = 'tabloid'

# UI Colors (hex color codes)
COLOR_SELECTED = '#4CAF50'      # Green - selected pages
COLOR_SPREAD = '#FFEB3B'        # Yellow - double-page spreads
COLOR_PENDING = '#FF9800'       # Orange - pending spread selection
COLOR_WARNING = '#D32F2F'       # Red - warnings and errors

# Thumbnail settings
THUMBNAIL_SIZE = (100, 140)     # Width x Height in pixels
PREVIEW_SIZE = (350, 500)       # Width x Height in pixels
GRID_COLUMNS = 6                # Number of columns in thumbnail grid

# Image processing
IMAGE_EXTENSIONS: Set[str] = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

# Split detection threshold
SPLIT_WIDTH_MULTIPLIER = 1.5    # Pages wider than standard_width * 1.5 are considered double-page

# Crop settings
COLOR_CROP = '#9C27B0'          # Purple - cropped pages (watermark removal)
MAX_CROP_PERCENT = 30           # Maximum crop percentage allowed
CROP_PREVIEW_SIZE = (200, 300)  # Crop dialog preview size (width x height in pixels)

# Cover tag colors
COLOR_FRONT_COVER = '#2196F3'   # Blue - front cover
COLOR_BACK_COVER = '#009688'    # Teal - back cover


@dataclass
class UITheme:
    """
    Centralized UI styling configuration.

    This dataclass encapsulates all UI theming properties, making it easy to
    add support for multiple themes (e.g., dark mode) in the future.
    """
    color_selected: str = COLOR_SELECTED
    color_spread: str = COLOR_SPREAD
    color_pending: str = COLOR_PENDING
    color_warning: str = COLOR_WARNING
    color_crop: str = COLOR_CROP
    color_front_cover: str = COLOR_FRONT_COVER
    color_back_cover: str = COLOR_BACK_COVER
    highlight_thickness: int = 3

    def __post_init__(self):
        """Validate color codes."""
        for color_name in ['color_selected', 'color_spread', 'color_pending', 'color_warning',
                           'color_crop', 'color_front_cover', 'color_back_cover']:
            color_value = getattr(self, color_name)
            if not (color_value.startswith('#') and len(color_value) == 7):
                raise ValueError(f"{color_name} must be a valid hex color code (e.g., #RRGGBB)")
