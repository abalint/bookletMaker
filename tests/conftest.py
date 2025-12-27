"""
Pytest configuration and fixtures.
"""

import pytest
from pathlib import Path


@pytest.fixture
def sample_pages():
    """Sample page list for testing."""
    return [1, 2, 3, 4, 5, 6, 7, 8]


@pytest.fixture
def temp_pdf_path(tmp_path):
    """Create a temporary PDF path for testing."""
    return tmp_path / "test.pdf"


@pytest.fixture
def sample_selection_string():
    """Sample page selection string."""
    return "1-8"
