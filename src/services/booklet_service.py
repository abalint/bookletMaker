"""
Booklet Service - High-level booklet generation operations.

This service coordinates PDF operations, handles file conversions,
manages temporary files, and provides error handling.
"""

from pathlib import Path
from typing import List, Dict, Any
from ..models import BookDefinition, BookletOptions


class BookletService:
    """
    High-level service for booklet operations.

    Handles file conversions, temp file cleanup, error handling, and
    coordinates between GUI and backend PDF operations.
    """

    def __init__(self):
        self._temp_files: List[Path] = []

    def generate_booklets(
        self,
        source_path: Path,
        books: List[BookDefinition],
        options: BookletOptions
    ) -> List[Path]:
        """
        Generate booklet PDFs for all books.

        Args:
            source_path: Path to source PDF/CBZ file
            books: List of book definitions with page selections
            options: Generation options (reading order, signatures, etc.)

        Returns:
            List of generated output file paths

        Raises:
            ValueError: If source file doesn't exist or is invalid format
            RuntimeError: If booklet generation fails
        """
        # Validate source file
        if not source_path.exists():
            raise ValueError(f"Source file not found: {source_path}")

        # Handle CBZ conversion if needed
        pdf_path = source_path
        if source_path.suffix.lower() == '.cbz':
            pdf_path = self._convert_cbz_to_pdf(source_path)

        # Import here to avoid circular dependency and to allow
        # booklet_maker to be optional for unit tests
        from booklet_maker import generate_booklet

        # Generate booklets
        try:
            output_files = generate_booklet(
                input_path=str(pdf_path),
                page_selections=[book.selection_string for book in books],
                reading_order=options.reading_order.value,
                num_signatures=options.num_signatures,
                duplex_mode=options.duplex_mode.value,
                output_name=options.output_name,
                paper_size=options.paper_size,
                output_dir=options.output_folder
            )

            return [Path(f) for f in output_files]

        except Exception as e:
            raise RuntimeError(f"Booklet generation failed: {str(e)}") from e

    def _convert_cbz_to_pdf(self, cbz_path: Path) -> Path:
        """
        Convert CBZ to temp PDF and track for cleanup.

        Args:
            cbz_path: Path to CBZ file

        Returns:
            Path to temporary PDF file

        Raises:
            ValueError: If CBZ conversion fails
        """
        try:
            from booklet_maker import cbz_to_pdf

            temp_pdf = Path(cbz_to_pdf(str(cbz_path)))
            self._temp_files.append(temp_pdf)
            return temp_pdf

        except Exception as e:
            raise ValueError(f"CBZ conversion failed: {str(e)}") from e

    def split_double_pages(self, pdf_path: Path, output_path: Path = None) -> Dict[str, Any]:
        """
        Split double-page spreads and return result.

        Args:
            pdf_path: Path to PDF file
            output_path: Optional output path (defaults to pdf_path with _split suffix)

        Returns:
            Dictionary with split results:
            - original_pages: int
            - output_pages: int
            - splits_made: int
            - split_pairs: List[Tuple[int, int]]
            - output_path: str

        Raises:
            RuntimeError: If PyMuPDF is not available
            ValueError: If split operation fails
        """
        if not pdf_path.exists():
            raise ValueError(f"PDF file not found: {pdf_path}")

        try:
            from booklet_maker import split_double_pages, PYMUPDF_AVAILABLE

            if not PYMUPDF_AVAILABLE:
                raise RuntimeError(
                    "PyMuPDF is required for splitting double pages. "
                    "Install with: pip install PyMuPDF"
                )

            result = split_double_pages(str(pdf_path), str(output_path) if output_path else None)
            return result

        except Exception as e:
            if "PyMuPDF" in str(e):
                raise RuntimeError(str(e)) from e
            raise ValueError(f"Split operation failed: {str(e)}") from e

    def cleanup(self):
        """
        Clean up temporary files created during operations.

        This should be called when the application exits or when
        temporary files are no longer needed.
        """
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                # Log but don't raise - cleanup is best-effort
                print(f"Warning: Failed to delete temp file {temp_file}: {e}")

        self._temp_files.clear()

    def get_temp_files(self) -> List[Path]:
        """
        Get list of temporary files being managed.

        Returns:
            List of temporary file paths
        """
        return self._temp_files.copy()
