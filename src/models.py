"""
Data models for the booklet maker.

This module defines typed dataclasses that replace dictionaries and tuples
throughout the codebase, improving type safety and code clarity.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class ReadingOrder(Enum):
    """Reading order for booklet page layout."""
    WESTERN = "western"  # Left-to-right reading (Western comics)
    MANGA = "manga"      # Right-to-left reading (Manga)


class DuplexMode(Enum):
    """Printing duplex mode."""
    AUTO = "auto"      # Single file with alternating front/back pages
    MANUAL = "manual"  # Separate files for front and back pages


@dataclass
class BookDefinition:
    """
    Represents a single book with its page selection.

    A book is a collection of pages from the source PDF that will be
    printed as a separate booklet.
    """
    name: str                # Display name (e.g., "Book 1", "Chapters 1-5")
    selection_string: str    # Page selection (e.g., "1-20,b,25-30")

    def __repr__(self):
        return f"BookDefinition(name='{self.name}', selection='{self.selection_string}')"


@dataclass
class BookletOptions:
    """
    Configuration for booklet generation.

    These options control how the booklet is laid out and printed.
    """
    reading_order: ReadingOrder = ReadingOrder.WESTERN
    num_signatures: int = 1
    duplex_mode: DuplexMode = DuplexMode.AUTO
    paper_size: str = "tabloid"
    output_name: str = ""
    output_folder: str = ""

    def __post_init__(self):
        """Validate options."""
        if self.num_signatures < 1:
            raise ValueError("num_signatures must be >= 1")
        if self.num_signatures > 10:
            raise ValueError("num_signatures must be <= 10")


@dataclass
class SpreadPair:
    """
    Represents a double-page spread.

    A spread pair indicates two pages that should be printed adjacent
    to each other for proper viewing when the booklet is opened.
    """
    left_page: int   # Page number on the left side
    right_page: int  # Page number on the right side

    def __post_init__(self):
        """Validate and normalize spread pair."""
        # Ensure pages are adjacent
        if abs(self.left_page - self.right_page) != 1:
            raise ValueError(
                f"Spread pages must be adjacent, got {self.left_page} and {self.right_page}"
            )

        # Normalize: ensure left < right
        if self.left_page > self.right_page:
            self.left_page, self.right_page = self.right_page, self.left_page

    def contains(self, page_num: int) -> bool:
        """Check if a page number is part of this spread."""
        return page_num in (self.left_page, self.right_page)

    def __repr__(self):
        return f"SpreadPair({self.left_page}, {self.right_page})"

    def as_tuple(self) -> tuple:
        """Return as tuple for backward compatibility."""
        return (self.left_page, self.right_page)


@dataclass
class ValidationResult:
    """
    Result of validation checks.

    Contains validation status, errors, and warnings that can be
    displayed to the user.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, message: str):
        """Add an error message and mark as invalid."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        """Add a warning message."""
        self.warnings.append(message)

    def has_issues(self) -> bool:
        """Check if there are any errors or warnings."""
        return len(self.errors) > 0 or len(self.warnings) > 0

    def get_summary(self) -> str:
        """Get a human-readable summary of validation results."""
        if self.is_valid and not self.warnings:
            return "Validation passed with no issues"

        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")

        return ", ".join(parts)

    def __repr__(self):
        return f"ValidationResult(is_valid={self.is_valid}, {self.get_summary()})"


@dataclass
class PageCropData:
    """
    Crop settings for a single page.

    Supports cropping from all four sides. Each value represents the
    percentage of the page dimension to remove from that edge.
    """
    page_num: int                    # Page number to crop (1-indexed)
    crop_top_percent: float = 0.0    # Percentage to crop from top (0-30%)
    crop_bottom_percent: float = 0.0 # Percentage to crop from bottom (0-30%)
    crop_left_percent: float = 0.0   # Percentage to crop from left (0-30%)
    crop_right_percent: float = 0.0  # Percentage to crop from right (0-30%)

    def __post_init__(self):
        """Validate crop settings."""
        for field_name in ['crop_top_percent', 'crop_bottom_percent',
                           'crop_left_percent', 'crop_right_percent']:
            value = getattr(self, field_name)
            if not 0 <= value <= 30:
                raise ValueError(
                    f"{field_name} must be between 0 and 30, got {value}"
                )

        # Ensure minimum visible area (at least 40% of each dimension)
        if self.crop_top_percent + self.crop_bottom_percent > 60:
            raise ValueError("Combined vertical crop cannot exceed 60%")
        if self.crop_left_percent + self.crop_right_percent > 60:
            raise ValueError("Combined horizontal crop cannot exceed 60%")

    def has_crop(self) -> bool:
        """Check if any cropping is applied."""
        return any([
            self.crop_top_percent > 0,
            self.crop_bottom_percent > 0,
            self.crop_left_percent > 0,
            self.crop_right_percent > 0
        ])

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'top': self.crop_top_percent,
            'bottom': self.crop_bottom_percent,
            'left': self.crop_left_percent,
            'right': self.crop_right_percent
        }

    @classmethod
    def from_dict(cls, page_num: int, data: dict) -> 'PageCropData':
        """Create from dictionary."""
        return cls(
            page_num=page_num,
            crop_top_percent=data.get('top', 0.0),
            crop_bottom_percent=data.get('bottom', 0.0),
            crop_left_percent=data.get('left', 0.0),
            crop_right_percent=data.get('right', 0.0)
        )


@dataclass
class CropDefaults:
    """Default crop values for new pages."""
    top: float = 0.0
    bottom: float = 0.0
    left: float = 0.0
    right: float = 0.0

    def __post_init__(self):
        """Validate default values."""
        for field_name in ['top', 'bottom', 'left', 'right']:
            value = getattr(self, field_name)
            if not 0 <= value <= 30:
                raise ValueError(f"{field_name} must be between 0 and 30, got {value}")

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {'top': self.top, 'bottom': self.bottom,
                'left': self.left, 'right': self.right}

    @classmethod
    def from_dict(cls, data: dict) -> 'CropDefaults':
        """Create from dictionary."""
        return cls(
            top=data.get('top', 0.0),
            bottom=data.get('bottom', 0.0),
            left=data.get('left', 0.0),
            right=data.get('right', 0.0)
        )
