"""
Crop Service - Handles page cropping operations for watermark removal.

This service provides methods to crop images and PDF pages, particularly
for removing watermarks from the bottom of pages.
"""

import os
import tempfile
from pathlib import Path
from typing import List
from PIL import Image


class CropService:
    """
    Service for cropping images and PDF pages.

    Provides lossless PDF cropping using PyMuPDF's CropBox functionality
    and PIL-based image cropping for preview purposes.
    """

    def crop_image(self, image: Image.Image, crop_bottom_percent: float) -> Image.Image:
        """
        Crop PIL Image from bottom by percentage (for dialog preview).

        Args:
            image: PIL Image to crop
            crop_bottom_percent: Percentage of height to crop from bottom (0-30%)

        Returns:
            Cropped PIL Image

        Example:
            >>> service = CropService()
            >>> img = Image.new('RGB', (100, 100))
            >>> cropped = service.crop_image(img, 10.0)  # Crop 10% from bottom
            >>> cropped.size
            (100, 90)
        """
        width, height = image.size
        crop_pixels = int(height * crop_bottom_percent / 100)
        new_height = height - crop_pixels

        # Crop: (left, top, right, bottom)
        return image.crop((0, 0, width, new_height))

    def apply_crops_to_pdf(
        self,
        pdf_path: Path,
        crops: List,
        output_path: Path = None
    ) -> Path:
        """
        Apply multiple crops to PDF pages using PyMuPDF CropBox (lossless).

        This method modifies the PDF's page MediaBox/CropBox directly without
        re-rendering, maintaining the original quality.

        Args:
            pdf_path: Path to input PDF file
            crops: List of PageCropData objects specifying pages to crop
            output_path: Optional output path (if None, creates temp file)

        Returns:
            Path to cropped PDF file

        Raises:
            FileNotFoundError: If pdf_path doesn't exist
            RuntimeError: If PyMuPDF operations fail

        Example:
            >>> from src.models import PageCropData
            >>> service = CropService()
            >>> crops = [PageCropData(page_num=1, crop_bottom_percent=10.0)]
            >>> output = service.apply_crops_to_pdf(Path('input.pdf'), crops)
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF is required for cropping PDF pages. "
                "Install with: pip install PyMuPDF"
            )

        from ..models import PageCropData

        try:
            # Open PDF document
            doc = fitz.open(str(pdf_path))

            # Apply each crop
            for crop in crops:
                if not isinstance(crop, PageCropData):
                    raise TypeError(f"Expected PageCropData, got {type(crop)}")

                # Validate page number
                if crop.page_num < 1 or crop.page_num > len(doc):
                    print(f"Warning: Page {crop.page_num} out of range (1-{len(doc)}), skipping")
                    continue

                # Get page (convert to 0-indexed)
                page = doc[crop.page_num - 1]

                # Get current page rectangle
                rect = page.rect

                # Calculate new rectangle (crop from bottom)
                crop_height = rect.height * (crop.crop_bottom_percent / 100)
                new_rect = fitz.Rect(
                    rect.x0,                    # Left (unchanged)
                    rect.y0,                    # Top (unchanged)
                    rect.x1,                    # Right (unchanged)
                    rect.y1 - crop_height       # Bottom (reduced)
                )

                # Apply crop by setting CropBox
                page.set_cropbox(new_rect)

            # Determine output path
            if output_path is None:
                # Create temp file
                fd, temp_path = tempfile.mkstemp(suffix='.pdf', prefix='cropped_')
                os.close(fd)  # Close file descriptor
                output_path = Path(temp_path)

            # Save cropped PDF
            doc.save(str(output_path))
            doc.close()

            return output_path

        except Exception as e:
            # Ensure document is closed on error
            if 'doc' in locals():
                doc.close()
            raise RuntimeError(f"Failed to apply crops to PDF: {e}") from e

    def get_temp_files(self) -> List[Path]:
        """
        Get list of temporary files created by this service.

        Returns:
            List of temporary file paths

        Note:
            Currently, temp files are created with tempfile.mkstemp() and
            are not tracked by this service. Cleanup should be handled by
            the caller using os.unlink() or similar.
        """
        # Note: This is a placeholder for future temp file tracking
        # Currently, temp files are managed by the caller
        return []
