"""
Tests for the crop service module.
"""

import pytest
from PIL import Image
from pathlib import Path
from src.services.crop_service import CropService
from src.models import PageCropData


class TestPageCropData:
    """Tests for PageCropData model."""

    def test_valid_crop_data(self):
        """Test creating valid crop data."""
        crop = PageCropData(page_num=1, crop_bottom_percent=10.0)
        assert crop.page_num == 1
        assert crop.crop_bottom_percent == 10.0

    def test_zero_percent_crop(self):
        """Test that 0% crop is valid."""
        crop = PageCropData(page_num=1, crop_bottom_percent=0.0)
        assert crop.crop_bottom_percent == 0.0

    def test_max_percent_crop(self):
        """Test that 30% crop is valid."""
        crop = PageCropData(page_num=1, crop_bottom_percent=30.0)
        assert crop.crop_bottom_percent == 30.0

    def test_invalid_crop_too_high(self):
        """Test that >30% crop raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 30"):
            PageCropData(page_num=1, crop_bottom_percent=50.0)

    def test_invalid_crop_negative(self):
        """Test that negative crop raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 30"):
            PageCropData(page_num=1, crop_bottom_percent=-5.0)


class TestCropService:
    """Tests for CropService."""

    def test_service_initialization(self):
        """Test that service initializes correctly."""
        service = CropService()
        assert service is not None

    def test_crop_image_10_percent(self):
        """Test cropping image by 10% from bottom."""
        service = CropService()
        image = Image.new('RGB', (100, 100), color='white')

        cropped = service.crop_image(image, 10.0)

        assert cropped.size == (100, 90)  # Width unchanged, height reduced by 10%

    def test_crop_image_20_percent(self):
        """Test cropping image by 20% from bottom."""
        service = CropService()
        image = Image.new('RGB', (200, 200), color='blue')

        cropped = service.crop_image(image, 20.0)

        assert cropped.size == (200, 160)  # 20% of 200 = 40 pixels removed

    def test_crop_image_zero_percent(self):
        """Test that 0% crop returns same dimensions."""
        service = CropService()
        image = Image.new('RGB', (100, 100), color='red')

        cropped = service.crop_image(image, 0.0)

        assert cropped.size == image.size

    def test_crop_image_preserves_width(self):
        """Test that cropping only affects height."""
        service = CropService()
        image = Image.new('RGB', (300, 400), color='green')

        cropped = service.crop_image(image, 15.0)

        assert cropped.width == image.width  # Width unchanged
        assert cropped.height < image.height  # Height reduced

    def test_crop_image_different_sizes(self):
        """Test cropping images of various sizes."""
        service = CropService()

        test_cases = [
            ((50, 100), 10.0, (50, 90)),
            ((1000, 1500), 5.0, (1000, 1425)),
            ((640, 480), 25.0, (640, 360)),
        ]

        for original_size, crop_pct, expected_size in test_cases:
            img = Image.new('RGB', original_size)
            cropped = service.crop_image(img, crop_pct)
            assert cropped.size == expected_size

    def test_apply_crops_to_pdf_file_not_found(self):
        """Test that apply_crops_to_pdf raises error for missing file."""
        service = CropService()
        nonexistent = Path("/nonexistent/file.pdf")
        crops = [PageCropData(page_num=1, crop_bottom_percent=10.0)]

        with pytest.raises(FileNotFoundError, match="not found"):
            service.apply_crops_to_pdf(nonexistent, crops)

    def test_apply_crops_to_pdf_invalid_crop_type(self, tmp_path):
        """Test that apply_crops_to_pdf validates crop types."""
        service = CropService()

        # Create a minimal PDF for testing (if PyMuPDF is available)
        try:
            import fitz
            pdf_path = tmp_path / "test.pdf"
            doc = fitz.open()  # New empty PDF
            page = doc.new_page()  # Add a blank page
            doc.save(str(pdf_path))
            doc.close()

            # Try with invalid crop type
            invalid_crops = [{"page_num": 1, "crop": 10.0}]  # Dict instead of PageCropData

            with pytest.raises(TypeError, match="Expected PageCropData"):
                service.apply_crops_to_pdf(pdf_path, invalid_crops)

        except ImportError:
            pytest.skip("PyMuPDF not available")

    def test_get_temp_files(self):
        """Test getting temporary files list."""
        service = CropService()
        temp_files = service.get_temp_files()

        # Currently returns empty list (placeholder)
        assert isinstance(temp_files, list)
