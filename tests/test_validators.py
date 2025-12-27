"""
Tests for the validators module.
"""

import pytest
from src.validators import SpreadValidator
from src.models import SpreadPair, ValidationResult


class TestSpreadValidator:
    """Tests for SpreadValidator class."""

    def test_spread_alignment_valid(self):
        """Test that properly aligned spreads are detected as valid."""
        pages = [1, 2, 3, 4]
        spread = SpreadPair(2, 3)

        results = SpreadValidator.check_spread_alignment(pages, [spread])

        assert len(results) == 1
        spread_result, pos_left, pos_right, is_aligned = results[0]
        assert is_aligned
        assert pos_left == 1  # Index of page 2
        assert pos_right == 2  # Index of page 3

    def test_spread_alignment_invalid(self):
        """Test that misaligned spreads are detected as invalid."""
        pages = [1, 2, 3, 4]
        spread = SpreadPair(1, 2)  # At positions 0,1 - not aligned (need odd-even)

        results = SpreadValidator.check_spread_alignment(pages, [spread])

        assert len(results) == 1
        spread_result, pos_left, pos_right, is_aligned = results[0]
        assert not is_aligned
        assert pos_left == 0  # Index of page 1
        assert pos_right == 1  # Index of page 2

    def test_spread_not_in_selection(self):
        """Test that spreads not in selection are skipped."""
        pages = [1, 2, 3, 4]
        spread = SpreadPair(5, 6)  # Not in selection

        results = SpreadValidator.check_spread_alignment(pages, [spread])

        assert len(results) == 0  # Skipped

    def test_multiple_spreads(self):
        """Test checking multiple spreads at once."""
        pages = [1, 2, 3, 4, 5, 6]
        spreads = [
            SpreadPair(2, 3),  # Aligned at positions 1-2
            SpreadPair(4, 5),  # Aligned at positions 3-4
            SpreadPair(1, 2),  # Not aligned at positions 0-1
        ]

        results = SpreadValidator.check_spread_alignment(pages, spreads)

        assert len(results) == 3
        assert results[0][3]  # First spread is aligned
        assert results[1][3]  # Second spread is aligned
        assert not results[2][3]  # Third spread is not aligned

    def test_validate_selection_empty(self):
        """Test that empty selection is invalid."""
        result = SpreadValidator.validate_selection("", 10)

        assert not result.is_valid
        assert len(result.errors) > 0
        assert "empty" in result.errors[0].lower()

    def test_validate_booklet_options_invalid_signatures(self):
        """Test that invalid signature count is detected."""
        result = SpreadValidator.validate_booklet_options(20, 0, "western")

        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_booklet_options_invalid_reading_order(self):
        """Test that invalid reading order is detected."""
        result = SpreadValidator.validate_booklet_options(20, 1, "invalid")

        assert not result.is_valid
        assert "reading order" in result.errors[0].lower()

    def test_validate_booklet_options_warnings(self):
        """Test that warnings are generated for questionable options."""
        # Too many signatures for small booklet
        result = SpreadValidator.validate_booklet_options(8, 5, "western")

        assert len(result.warnings) > 0


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_add_error_marks_invalid(self):
        """Test that adding an error marks result as invalid."""
        result = ValidationResult(is_valid=True)

        result.add_error("Test error")

        assert not result.is_valid
        assert "Test error" in result.errors

    def test_add_warning_preserves_validity(self):
        """Test that warnings don't affect validity."""
        result = ValidationResult(is_valid=True)

        result.add_warning("Test warning")

        assert result.is_valid
        assert "Test warning" in result.warnings

    def test_get_summary(self):
        """Test summary generation."""
        result = ValidationResult(is_valid=False)
        result.errors.append("Error 1")
        result.warnings.append("Warning 1")

        summary = result.get_summary()

        assert "1 error(s)" in summary
        assert "1 warning(s)" in summary


class TestSpreadPair:
    """Tests for SpreadPair model."""

    def test_spread_pair_normalizes_order(self):
        """Test that spread pair normalizes page order."""
        spread = SpreadPair(3, 2)  # Right page given first

        assert spread.left_page == 2
        assert spread.right_page == 3

    def test_spread_pair_validates_adjacent(self):
        """Test that non-adjacent pages are rejected."""
        with pytest.raises(ValueError, match="adjacent"):
            SpreadPair(1, 5)  # Pages must be adjacent

    def test_spread_pair_contains(self):
        """Test contains method."""
        spread = SpreadPair(2, 3)

        assert spread.contains(2)
        assert spread.contains(3)
        assert not spread.contains(1)
        assert not spread.contains(4)

    def test_spread_pair_as_tuple(self):
        """Test conversion to tuple."""
        spread = SpreadPair(2, 3)

        assert spread.as_tuple() == (2, 3)
