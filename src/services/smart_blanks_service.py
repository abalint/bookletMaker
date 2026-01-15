"""
Smart blank page insertion service.

This service provides intelligent blank page insertion to optimize
booklet layout considering cover positions and double-page spread alignment.
"""

from typing import List, Tuple, Optional, Union


class SmartBlanksService:
    """Service for intelligent blank page insertion."""

    @staticmethod
    def calculate_smart_blanks(
        pages: List[Union[int, str]],
        front_cover: Optional[int],
        back_cover: Optional[int],
        spread_pairs: List[Tuple[int, int]]
    ) -> Tuple[List[Union[int, str]], List[str]]:
        """
        Calculate optimal blank insertion.

        Args:
            pages: Current page list (ints and "blank" strings)
            front_cover: Page number tagged as front cover (or None)
            back_cover: Page number tagged as back cover (or None)
            spread_pairs: List of (left_page, right_page) tuples

        Returns:
            Tuple of (modified_pages, change_descriptions)
        """
        result = list(pages)
        changes = []

        # Step 1: Handle front cover - should be at position 0
        if front_cover and front_cover in result:
            fc_pos = result.index(front_cover)
            if fc_pos > 0:
                # Insert blank at start to push front cover to position 1
                # (front cover stays at original position, blank goes before it)
                result.insert(0, "blank")
                changes.append(f"Added blank before front cover (page {front_cover})")

        # Step 2: Fix spread alignment
        for left_page, right_page in spread_pairs:
            if left_page not in result or right_page not in result:
                continue

            left_pos = result.index(left_page)
            right_pos = result.index(right_page)

            # Spreads need left page at odd 0-indexed position (even 1-indexed)
            # so they appear side-by-side when folded
            if abs(left_pos - right_pos) == 1:  # Pages are adjacent
                if left_pos % 2 == 0:  # Left at even position - needs shift
                    result.insert(left_pos, "blank")
                    changes.append(f"Added blank to align spread ({left_page}-{right_page})")

        # Step 3: Calculate pages needed (multiple of 4)
        target_count = ((len(result) + 3) // 4) * 4
        blanks_needed = target_count - len(result)

        # Step 4: Handle back cover positioning
        if back_cover and back_cover in result:
            bc_pos = result.index(back_cover)
            # Back cover should be at last position
            blanks_before_back = (target_count - 1) - bc_pos
            if blanks_before_back > 0:
                for _ in range(blanks_before_back):
                    result.insert(bc_pos, "blank")
                changes.append(f"Added {blanks_before_back} blank(s) to position back cover last")
        elif blanks_needed > 0:
            # No back cover - append blanks at end
            for _ in range(blanks_needed):
                result.append("blank")
            changes.append(f"Added {blanks_needed} blank(s) to fill booklet")

        return result, changes
