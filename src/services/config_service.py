"""
Configuration Service - Manages application settings persistence.

This service handles loading and saving user configuration to/from config.json,
with proper validation and defaults.
"""

import json
from pathlib import Path
from typing import Optional
from ..models import BookletOptions, ReadingOrder, DuplexMode
from ..config import DEFAULT_PAPER_SIZE


class ConfigService:
    """
    Manages application configuration persistence.

    Handles loading configuration from config.json, saving changes,
    and providing sensible defaults when config doesn't exist.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize config service.

        Args:
            config_path: Optional custom config file path.
                        If None, uses config.json in project root.
        """
        if config_path is None:
            # Default to config.json in same directory as this file's parent (project root)
            config_path = Path(__file__).parent.parent.parent / "config.json"

        self.config_path = config_path

    def load(self) -> BookletOptions:
        """
        Load configuration from file.

        Returns:
            BookletOptions with loaded settings, or defaults if file doesn't exist

        Note:
            If config file doesn't exist or is invalid, returns default options.
            Errors are silently handled to provide graceful degradation.
        """
        # Return defaults if file doesn't exist
        if not self.config_path.exists():
            return BookletOptions()

        try:
            with open(self.config_path) as f:
                data = json.load(f)

            # Parse and validate
            return BookletOptions(
                reading_order=ReadingOrder(data.get('reading_order', 'western')),
                num_signatures=data.get('signatures', 1),
                duplex_mode=DuplexMode(data.get('duplex_mode', 'auto')),
                paper_size=data.get('paper_size', DEFAULT_PAPER_SIZE),
                output_folder=data.get('output_folder', '')
            )

        except (json.JSONDecodeError, IOError, ValueError, KeyError) as e:
            # If config is corrupted or invalid, return defaults
            print(f"Warning: Failed to load config from {self.config_path}: {e}")
            print("Using default configuration")
            return BookletOptions()

    def save(self, options: BookletOptions):
        """
        Save configuration to file.

        Args:
            options: BookletOptions to save

        Note:
            Failures are silently handled - config saving is best-effort.
            The application should work even if config can't be saved.
        """
        # Convert to JSON-serializable dict
        data = {
            'reading_order': options.reading_order.value,
            'signatures': options.num_signatures,
            'duplex_mode': options.duplex_mode.value,
            'paper_size': options.paper_size,
            'output_folder': options.output_folder
        }

        try:
            # Ensure parent directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write with indentation for readability
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)

        except (IOError, OSError) as e:
            # Log but don't raise - saving config is not critical
            print(f"Warning: Failed to save config to {self.config_path}: {e}")

    def reset_to_defaults(self):
        """
        Delete config file to reset to defaults.

        Returns:
            True if config was deleted, False if it didn't exist or couldn't be deleted
        """
        try:
            if self.config_path.exists():
                self.config_path.unlink()
                return True
            return False

        except (IOError, OSError) as e:
            print(f"Warning: Failed to delete config file {self.config_path}: {e}")
            return False

    def get_config_path(self) -> Path:
        """
        Get the path to the configuration file.

        Returns:
            Path to config file (may not exist yet)
        """
        return self.config_path
