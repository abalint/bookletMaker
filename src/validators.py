"""
Business logic validators for booklet generation.

This module contains validation logic extracted from the GUI, making it
testable and reusable. These validators ensure booklet integrity and
provide helpful error messages to users.
"""

from typing import List, Tuple
from .models import SpreadPair, ValidationResult


class SpreadValidator:
    """Validates spread alignment in booklet layout."""

    @staticmethod
    def check_spread_alignment(
        pages: List[int],
        spreads: List[SpreadPair]
    ) -> List[Tuple[SpreadPair, int, int, bool]]:
        """
        Check if marked spreads will print correctly aligned.

        In a properly formatted booklet, spread pairs must appear at positions
        where they'll be printed side-by-side. This means they need to be at
        odd-even consecutive positions (1-2, 3-4, 5-6, etc.) after accounting
        for booklet page ordering.

        Args:
            pages: List of page numbers in booklet order (1-indexed)
            spreads: List of SpreadPair objects representing double-page spreads

        Returns:
            List of tuples containing:
            - spread: The SpreadPair object
            - pos_left: Position index of left page in the pages list
            - pos_right: Position index of right page in the pages list
            - is_aligned: True if spread will print correctly aligned

        Example:
            >>> pages = [1, 2, 3, 4]
            >>> spreads = [SpreadPair(2, 3)]
            >>> results = SpreadValidator.check_spread_alignment(pages, spreads)
            >>> # Result: [(SpreadPair(2,3), 1, 2, True)]
            >>> # Positions 1-2 are aligned (pages 2-3 will print side-by-side)
        """
        results = []

        for spread in spreads:
            # Find positions of spread pages in the selection
            pos_left = None
            pos_right = None

            for i, page_num in enumerate(pages):
                if page_num == spread.left_page:
                    pos_left = i
                if page_num == spread.right_page:
                    pos_right = i

            # Skip if spread pages not in selection
            if pos_left is None or pos_right is None:
                continue

            # Check alignment: pages must be at consecutive odd-even positions
            # Position 1 (odd) + Position 2 (even) = aligned
            # Position 3 (odd) + Position 4 (even) = aligned
            # etc.
            is_aligned = (
                (pos_left % 2 == 1 and pos_right == pos_left + 1) or
                (pos_right % 2 == 1 and pos_left == pos_right + 1)
            )

            results.append((spread, pos_left, pos_right, is_aligned))

        return results

    @staticmethod
    def validate_selection(
        selection_str: str,
        total_pages: int
    ) -> ValidationResult:
        """
        Validate page selection string.

        Args:
            selection_str: Page selection string (e.g., "1-20,b,25-30")
            total_pages: Total number of pages in the PDF

        Returns:
            ValidationResult with any errors or warnings
        """
        result = ValidationResult(is_valid=True)

        if not selection_str or not selection_str.strip():
            result.add_error("Page selection cannot be empty")
            return result

        # Try to parse the selection
        try:
            # Import here to avoid circular dependency
            from booklet_maker import parse_page_selection

            pages = parse_page_selection(selection_str, total_pages)

            if not pages:
                result.add_error("No pages selected (selection parsed to empty list)")

            # Warn if selection is very large
            if len(pages) > 200:
                result.add_warning(
                    f"Large selection ({len(pages)} pages) may result in a thick booklet that's difficult to bind"
                )

        except Exception as e:
            result.add_error(f"Invalid page selection: {str(e)}")

        return result

    @staticmethod
    def validate_booklet_options(
        num_pages: int,
        num_signatures: int,
        reading_order: str
    ) -> ValidationResult:
        """
        Validate booklet generation options.

        Args:
            num_pages: Number of pages in the selection
            num_signatures: Number of signatures to split into
            reading_order: Reading order ('western' or 'manga')

        Returns:
            ValidationResult with any errors or warnings
        """
        result = ValidationResult(is_valid=True)

        # Validate signatures
        if num_signatures < 1:
            result.add_error("Number of signatures must be at least 1")
        elif num_signatures > 10:
            result.add_warning(
                f"Very large number of signatures ({num_signatures}) may result in thin, fragile booklets"
            )

        # Validate reading order
        if reading_order not in ('western', 'manga'):
            result.add_error(f"Invalid reading order: '{reading_order}'. Must be 'western' or 'manga'")

        # Warn about signature distribution
        if num_pages > 0 and num_signatures > 1:
            pages_per_sig = num_pages / num_signatures
            if pages_per_sig < 4:
                result.add_warning(
                    f"Each signature will have only ~{pages_per_sig:.1f} pages. Consider reducing signature count."
                )

        return result
