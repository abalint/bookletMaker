"""
Tests for the services module.
"""

import pytest
import json
from pathlib import Path
from src.services.config_service import ConfigService
from src.services.booklet_service import BookletService
from src.models import BookletOptions, ReadingOrder, DuplexMode, BookDefinition


class TestConfigService:
    """Tests for ConfigService."""

    def test_save_and_load(self, tmp_path):
        """Test that config can be saved and loaded."""
        config_path = tmp_path / "config.json"
        service = ConfigService(config_path)

        # Create options
        options = BookletOptions(
            reading_order=ReadingOrder.MANGA,
            num_signatures=2,
            paper_size='a4',
            output_folder='/test/path'
        )

        # Save
        service.save(options)
        assert config_path.exists()

        # Load
        loaded = service.load()
        assert loaded.reading_order == ReadingOrder.MANGA
        assert loaded.num_signatures == 2
        assert loaded.paper_size == 'a4'
        assert loaded.output_folder == '/test/path'

    def test_load_nonexistent_returns_defaults(self, tmp_path):
        """Test that loading nonexistent config returns defaults."""
        config_path = tmp_path / "nonexistent.json"
        service = ConfigService(config_path)

        loaded = service.load()

        assert isinstance(loaded, BookletOptions)
        assert loaded.reading_order == ReadingOrder.WESTERN
        assert loaded.num_signatures == 1
        assert loaded.duplex_mode == DuplexMode.AUTO

    def test_load_corrupted_returns_defaults(self, tmp_path):
        """Test that corrupted config falls back to defaults."""
        config_path = tmp_path / "config.json"

        # Write invalid JSON
        with open(config_path, 'w') as f:
            f.write("{ invalid json }")

        service = ConfigService(config_path)
        loaded = service.load()

        # Should return defaults
        assert isinstance(loaded, BookletOptions)
        assert loaded.num_signatures == 1

    def test_reset_to_defaults(self, tmp_path):
        """Test resetting config to defaults."""
        config_path = tmp_path / "config.json"
        service = ConfigService(config_path)

        # Save a config
        service.save(BookletOptions(num_signatures=5))
        assert config_path.exists()

        # Reset
        result = service.reset_to_defaults()
        assert result  # Returns True when file was deleted
        assert not config_path.exists()

        # Reset again (file doesn't exist)
        result = service.reset_to_defaults()
        assert not result  # Returns False when file didn't exist

    def test_get_config_path(self, tmp_path):
        """Test getting config path."""
        config_path = tmp_path / "test.json"
        service = ConfigService(config_path)

        assert service.get_config_path() == config_path

    def test_save_creates_parent_directories(self, tmp_path):
        """Test that save creates parent directories if needed."""
        config_path = tmp_path / "subdir" / "config.json"
        service = ConfigService(config_path)

        options = BookletOptions()
        service.save(options)

        assert config_path.exists()
        assert config_path.parent.exists()


class TestBookletService:
    """Tests for BookletService."""

    def test_service_initialization(self):
        """Test that service initializes correctly."""
        service = BookletService()

        assert service._temp_files == []

    def test_get_temp_files(self):
        """Test getting temp files list."""
        service = BookletService()

        # Initially empty
        assert service.get_temp_files() == []

        # Add a temp file
        test_path = Path("/tmp/test.pdf")
        service._temp_files.append(test_path)

        # Should return copy
        temp_files = service.get_temp_files()
        assert test_path in temp_files

        # Modifying returned list shouldn't affect internal list
        temp_files.clear()
        assert len(service._temp_files) == 1

    def test_cleanup_removes_temp_files(self, tmp_path):
        """Test that cleanup removes temp files."""
        service = BookletService()

        # Create a temp file
        temp_file = tmp_path / "temp.pdf"
        temp_file.write_text("test")
        service._temp_files.append(temp_file)

        assert temp_file.exists()

        # Cleanup
        service.cleanup()

        assert not temp_file.exists()
        assert service._temp_files == []

    def test_cleanup_handles_missing_files(self, tmp_path):
        """Test that cleanup handles already-deleted files gracefully."""
        service = BookletService()

        # Add a file that doesn't exist
        nonexistent = tmp_path / "nonexistent.pdf"
        service._temp_files.append(nonexistent)

        # Should not raise
        service.cleanup()

        assert service._temp_files == []

    def test_split_double_pages_validates_path(self):
        """Test that split_double_pages validates file existence."""
        service = BookletService()
        nonexistent = Path("/nonexistent/file.pdf")

        with pytest.raises(ValueError, match="not found"):
            service.split_double_pages(nonexistent)


class TestBookDefinition:
    """Tests for BookDefinition model (service-related usage)."""

    def test_book_definition_creation(self):
        """Test creating book definitions."""
        book = BookDefinition(
            name="Test Book",
            selection_string="1-10,b,15-20"
        )

        assert book.name == "Test Book"
        assert book.selection_string == "1-10,b,15-20"

    def test_book_definition_repr(self):
        """Test string representation."""
        book = BookDefinition(name="Book 1", selection_string="1-5")

        repr_str = repr(book)
        assert "Book 1" in repr_str
        assert "1-5" in repr_str


class TestBookletOptions:
    """Tests for BookletOptions model (service-related usage)."""

    def test_options_validation(self):
        """Test that options validate properly."""
        # Valid options
        options = BookletOptions(num_signatures=5)
        assert options.num_signatures == 5

        # Invalid signatures (too few)
        with pytest.raises(ValueError, match="num_signatures must be >= 1"):
            BookletOptions(num_signatures=0)

        # Invalid signatures (too many)
        with pytest.raises(ValueError, match="num_signatures must be <= 10"):
            BookletOptions(num_signatures=11)

    def test_options_defaults(self):
        """Test default values."""
        options = BookletOptions()

        assert options.reading_order == ReadingOrder.WESTERN
        assert options.num_signatures == 1
        assert options.duplex_mode == DuplexMode.AUTO
        assert options.paper_size == "tabloid"
        assert options.output_name == ""
        assert options.output_folder == ""
