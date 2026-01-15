"""
Crop Service - Handles page cropping operations for watermark removal.

This service provides methods to crop images and PDF pages, particularly
for removing watermarks from the bottom of pages. Also supports stretching
cropped images back to original size.
"""

import os
import tempfile
from pathlib import Path
from typing import List, Tuple
from PIL import Image

from ..models import StretchMode


class CropService:
    """
    Service for cropping images and PDF pages.

    Provides lossless PDF cropping using PyMuPDF's CropBox functionality
    and PIL-based image cropping for preview purposes.
    """

    def crop_image(
        self,
        image: Image.Image,
        crop_top_percent: float = 0.0,
        crop_bottom_percent: float = 0.0,
        crop_left_percent: float = 0.0,
        crop_right_percent: float = 0.0
    ) -> Image.Image:
        """
        Crop PIL Image from all four sides by percentage (for dialog preview).

        Args:
            image: PIL Image to crop
            crop_top_percent: Percentage of height to crop from top (0-30%)
            crop_bottom_percent: Percentage of height to crop from bottom (0-30%)
            crop_left_percent: Percentage of width to crop from left (0-30%)
            crop_right_percent: Percentage of width to crop from right (0-30%)

        Returns:
            Cropped PIL Image

        Example:
            >>> service = CropService()
            >>> img = Image.new('RGB', (100, 100))
            >>> cropped = service.crop_image(img, crop_bottom_percent=10.0)
            >>> cropped.size
            (100, 90)
            >>> cropped = service.crop_image(img, crop_top_percent=10.0, crop_bottom_percent=10.0,
            ...                               crop_left_percent=10.0, crop_right_percent=10.0)
            >>> cropped.size
            (80, 80)
        """
        width, height = image.size

        # Calculate pixel offsets
        top_pixels = int(height * crop_top_percent / 100)
        bottom_pixels = int(height * crop_bottom_percent / 100)
        left_pixels = int(width * crop_left_percent / 100)
        right_pixels = int(width * crop_right_percent / 100)

        # New crop boundaries
        new_left = left_pixels
        new_top = top_pixels
        new_right = width - right_pixels
        new_bottom = height - bottom_pixels

        # Crop: (left, top, right, bottom)
        return image.crop((new_left, new_top, new_right, new_bottom))

    def stretch_image(
        self,
        image: Image.Image,
        original_size: Tuple[int, int],
        stretch_mode: StretchMode
    ) -> Image.Image:
        """
        Stretch a cropped image according to the specified mode.

        Args:
            image: Cropped PIL Image to stretch
            original_size: Original (width, height) before cropping
            stretch_mode: How to stretch the image

        Returns:
            Stretched PIL Image

        Example:
            >>> service = CropService()
            >>> img = Image.new('RGB', (80, 90))  # Cropped image
            >>> stretched = service.stretch_image(img, (100, 100), StretchMode.FILL)
            >>> stretched.size
            (100, 100)
        """
        if stretch_mode == StretchMode.NONE:
            return image

        current_width, current_height = image.size
        target_width, target_height = original_size

        if stretch_mode == StretchMode.HORIZONTAL:
            # Stretch width only, keep height
            new_size = (target_width, current_height)
        elif stretch_mode == StretchMode.VERTICAL:
            # Stretch height only, keep width
            new_size = (current_width, target_height)
        elif stretch_mode == StretchMode.FILL:
            # Stretch to fill original size (may distort aspect ratio)
            new_size = (target_width, target_height)
        elif stretch_mode == StretchMode.FIT:
            # Scale uniformly to fit within original size (preserve aspect ratio)
            scale_w = target_width / current_width
            scale_h = target_height / current_height
            scale = min(scale_w, scale_h)
            new_size = (int(current_width * scale), int(current_height * scale))
        else:
            return image

        return image.resize(new_size, Image.Resampling.LANCZOS)

    def crop_and_stretch_image(
        self,
        image: Image.Image,
        crop_top_percent: float = 0.0,
        crop_bottom_percent: float = 0.0,
        crop_left_percent: float = 0.0,
        crop_right_percent: float = 0.0,
        stretch_mode: StretchMode = StretchMode.NONE
    ) -> Image.Image:
        """
        Crop and then stretch an image in a single operation.

        Args:
            image: PIL Image to process
            crop_top_percent: Percentage to crop from top
            crop_bottom_percent: Percentage to crop from bottom
            crop_left_percent: Percentage to crop from left
            crop_right_percent: Percentage to crop from right
            stretch_mode: How to stretch after cropping

        Returns:
            Cropped and stretched PIL Image
        """
        original_size = image.size

        # First crop
        cropped = self.crop_image(
            image,
            crop_top_percent=crop_top_percent,
            crop_bottom_percent=crop_bottom_percent,
            crop_left_percent=crop_left_percent,
            crop_right_percent=crop_right_percent
        )

        # Then stretch
        return self.stretch_image(cropped, original_size, stretch_mode)

    def apply_crops_to_pdf(
        self,
        pdf_path: Path,
        crops: List,
        output_path: Path = None
    ) -> Path:
        """
        Apply multiple crops (and optional stretching) to PDF pages.

        For pages without stretching, uses lossless CropBox modification.
        For pages with stretching, re-renders the content at the stretched size.

        Args:
            pdf_path: Path to input PDF file
            crops: List of PageCropData objects specifying pages to crop/stretch
            output_path: Optional output path (if None, creates temp file)

        Returns:
            Path to processed PDF file

        Raises:
            FileNotFoundError: If pdf_path doesn't exist
            RuntimeError: If PyMuPDF operations fail

        Example:
            >>> from src.models import PageCropData, StretchMode
            >>> service = CropService()
            >>> crops = [PageCropData(page_num=1, crop_bottom_percent=10.0, stretch_mode=StretchMode.FILL)]
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

            # Build a map of page_num -> crop data for pages needing stretch
            stretch_pages = {}
            for crop in crops:
                if not isinstance(crop, PageCropData):
                    raise TypeError(f"Expected PageCropData, got {type(crop)}")
                if crop.stretch_mode != StretchMode.NONE:
                    stretch_pages[crop.page_num] = crop

            # If any pages need stretching, we need to rebuild the document
            if stretch_pages:
                doc = self._apply_crops_with_stretch(doc, crops, fitz)
            else:
                # Simple case: just apply cropbox to each page (lossless)
                for crop in crops:
                    if crop.page_num < 1 or crop.page_num > len(doc):
                        print(f"Warning: Page {crop.page_num} out of range (1-{len(doc)}), skipping")
                        continue

                    page = doc[crop.page_num - 1]
                    rect = page.rect

                    crop_top = rect.height * (crop.crop_top_percent / 100)
                    crop_bottom = rect.height * (crop.crop_bottom_percent / 100)
                    crop_left = rect.width * (crop.crop_left_percent / 100)
                    crop_right = rect.width * (crop.crop_right_percent / 100)

                    new_rect = fitz.Rect(
                        rect.x0 + crop_left,
                        rect.y0 + crop_top,
                        rect.x1 - crop_right,
                        rect.y1 - crop_bottom
                    )
                    page.set_cropbox(new_rect)

            # Determine output path
            if output_path is None:
                fd, temp_path = tempfile.mkstemp(suffix='.pdf', prefix='cropped_')
                os.close(fd)
                output_path = Path(temp_path)

            doc.save(str(output_path))
            doc.close()

            return output_path

        except Exception as e:
            if 'doc' in locals():
                doc.close()
            raise RuntimeError(f"Failed to apply crops to PDF: {e}") from e

    def _apply_crops_with_stretch(self, doc, crops: List, fitz) -> 'fitz.Document':
        """
        Apply crops with stretching by rebuilding pages that need stretching.

        For stretched pages, renders the cropped content into a new page at the
        target size using show_pdf_page for vector-quality scaling.
        """
        from ..models import PageCropData

        # Create a mapping of page numbers to their crop data
        crop_map = {}
        for crop in crops:
            if isinstance(crop, PageCropData):
                crop_map[crop.page_num] = crop

        # Create output document
        out_doc = fitz.open()

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            src_page = doc[page_idx]
            original_rect = src_page.rect

            if page_num in crop_map:
                crop = crop_map[page_num]

                # Calculate cropped region
                crop_top = original_rect.height * (crop.crop_top_percent / 100)
                crop_bottom = original_rect.height * (crop.crop_bottom_percent / 100)
                crop_left = original_rect.width * (crop.crop_left_percent / 100)
                crop_right = original_rect.width * (crop.crop_right_percent / 100)

                cropped_rect = fitz.Rect(
                    original_rect.x0 + crop_left,
                    original_rect.y0 + crop_top,
                    original_rect.x1 - crop_right,
                    original_rect.y1 - crop_bottom
                )

                cropped_width = cropped_rect.width
                cropped_height = cropped_rect.height

                if crop.stretch_mode == StretchMode.NONE:
                    # No stretch - just crop (lossless)
                    new_page = out_doc.new_page(
                        width=cropped_width,
                        height=cropped_height
                    )
                    new_page.show_pdf_page(
                        new_page.rect,
                        doc,
                        page_idx,
                        clip=cropped_rect
                    )
                elif crop.stretch_mode == StretchMode.FILL:
                    # Stretch to fill original size
                    new_page = out_doc.new_page(
                        width=original_rect.width,
                        height=original_rect.height
                    )
                    new_page.show_pdf_page(
                        new_page.rect,
                        doc,
                        page_idx,
                        clip=cropped_rect
                    )
                elif crop.stretch_mode == StretchMode.HORIZONTAL:
                    # Stretch width only
                    new_page = out_doc.new_page(
                        width=original_rect.width,
                        height=cropped_height
                    )
                    new_page.show_pdf_page(
                        new_page.rect,
                        doc,
                        page_idx,
                        clip=cropped_rect
                    )
                elif crop.stretch_mode == StretchMode.VERTICAL:
                    # Stretch height only
                    new_page = out_doc.new_page(
                        width=cropped_width,
                        height=original_rect.height
                    )
                    new_page.show_pdf_page(
                        new_page.rect,
                        doc,
                        page_idx,
                        clip=cropped_rect
                    )
                elif crop.stretch_mode == StretchMode.FIT:
                    # Scale uniformly to fit within original size
                    scale_w = original_rect.width / cropped_width
                    scale_h = original_rect.height / cropped_height
                    scale = min(scale_w, scale_h)

                    target_width = cropped_width * scale
                    target_height = cropped_height * scale

                    new_page = out_doc.new_page(
                        width=original_rect.width,
                        height=original_rect.height
                    )
                    # Center the content
                    x_offset = (original_rect.width - target_width) / 2
                    y_offset = (original_rect.height - target_height) / 2
                    target_rect = fitz.Rect(
                        x_offset,
                        y_offset,
                        x_offset + target_width,
                        y_offset + target_height
                    )
                    new_page.show_pdf_page(
                        target_rect,
                        doc,
                        page_idx,
                        clip=cropped_rect
                    )
            else:
                # No crop for this page - copy as-is
                new_page = out_doc.new_page(
                    width=original_rect.width,
                    height=original_rect.height
                )
                new_page.show_pdf_page(new_page.rect, doc, page_idx)

        doc.close()
        return out_doc

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
