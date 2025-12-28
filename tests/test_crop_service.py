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

    def test_4_sided_crop_data(self):
        """Test creating 4-sided crop data."""
        crop = PageCropData(
            page_num=1,
            crop_top_percent=5.0,
            crop_bottom_percent=10.0,
            crop_left_percent=3.0,
            crop_right_percent=7.0
        )
        assert crop.page_num == 1
        assert crop.crop_top_percent == 5.0
        assert crop.crop_bottom_percent == 10.0
        assert crop.crop_left_percent == 3.0
        assert crop.crop_right_percent == 7.0

    def test_combined_vertical_crop_limit(self):
        """Test that combined vertical crop cannot exceed 60%."""
        with pytest.raises(ValueError, match="Combined vertical crop"):
            PageCropData(page_num=1, crop_top_percent=35.0, crop_bottom_percent=30.0)

    def test_combined_horizontal_crop_limit(self):
        """Test that combined horizontal crop cannot exceed 60%."""
        with pytest.raises(ValueError, match="Combined horizontal crop"):
            PageCropData(page_num=1, crop_left_percent=35.0, crop_right_percent=30.0)

    def test_max_combined_crop_valid(self):
        """Test that 60% combined crop is valid (boundary case)."""
        crop = PageCropData(page_num=1, crop_top_percent=30.0, crop_bottom_percent=30.0)
        assert crop.crop_top_percent == 30.0
        assert crop.crop_bottom_percent == 30.0

    def test_has_crop_true(self):
        """Test has_crop returns True when any crop is set."""
        crop = PageCropData(page_num=1, crop_bottom_percent=5.0)
        assert crop.has_crop() is True

    def test_has_crop_false(self):
        """Test has_crop returns False when no crop is set."""
        crop = PageCropData(page_num=1)
        assert crop.has_crop() is False

    def test_to_dict(self):
        """Test converting to dictionary."""
        crop = PageCropData(
            page_num=1,
            crop_top_percent=5.0,
            crop_bottom_percent=10.0,
            crop_left_percent=3.0,
            crop_right_percent=7.0
        )
        d = crop.to_dict()
        assert d == {'top': 5.0, 'bottom': 10.0, 'left': 3.0, 'right': 7.0}

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {'top': 5.0, 'bottom': 10.0, 'left': 3.0, 'right': 7.0}
        crop = PageCropData.from_dict(1, data)
        assert crop.page_num == 1
        assert crop.crop_top_percent == 5.0
        assert crop.crop_bottom_percent == 10.0
        assert crop.crop_left_percent == 3.0
        assert crop.crop_right_percent == 7.0

    def test_from_dict_partial(self):
        """Test creating from dictionary with missing keys."""
        data = {'bottom': 10.0}
        crop = PageCropData.from_dict(1, data)
        assert crop.crop_top_percent == 0.0
        assert crop.crop_bottom_percent == 10.0
        assert crop.crop_left_percent == 0.0
        assert crop.crop_right_percent == 0.0


class TestCropService:
    """Tests for CropService."""

    def test_service_initialization(self):
        """Test that service initializes correctly."""
        service = CropService()
        assert service is not None

    def test_crop_image_10_percent_bottom(self):
        """Test cropping image by 10% from bottom."""
        service = CropService()
        image = Image.new('RGB', (100, 100), color='white')

        cropped = service.crop_image(image, crop_bottom_percent=10.0)

        assert cropped.size == (100, 90)  # Width unchanged, height reduced by 10%

    def test_crop_image_20_percent_bottom(self):
        """Test cropping image by 20% from bottom."""
        service = CropService()
        image = Image.new('RGB', (200, 200), color='blue')

        cropped = service.crop_image(image, crop_bottom_percent=20.0)

        assert cropped.size == (200, 160)  # 20% of 200 = 40 pixels removed

    def test_crop_image_zero_percent(self):
        """Test that 0% crop returns same dimensions."""
        service = CropService()
        image = Image.new('RGB', (100, 100), color='red')

        cropped = service.crop_image(image)

        assert cropped.size == image.size

    def test_crop_image_preserves_width_bottom_only(self):
        """Test that bottom-only cropping only affects height."""
        service = CropService()
        image = Image.new('RGB', (300, 400), color='green')

        cropped = service.crop_image(image, crop_bottom_percent=15.0)

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
            cropped = service.crop_image(img, crop_bottom_percent=crop_pct)
            assert cropped.size == expected_size

    def test_crop_image_4_sides(self):
        """Test cropping from all four sides."""
        service = CropService()
        image = Image.new('RGB', (100, 100), color='white')

        cropped = service.crop_image(
            image,
            crop_top_percent=10.0,
            crop_bottom_percent=10.0,
            crop_left_percent=10.0,
            crop_right_percent=10.0
        )

        assert cropped.size == (80, 80)  # 10% from each side

    def test_crop_image_top_only(self):
        """Test cropping from top only."""
        service = CropService()
        image = Image.new('RGB', (100, 200), color='white')

        cropped = service.crop_image(image, crop_top_percent=25.0)

        assert cropped.size == (100, 150)  # 25% of 200 = 50 pixels removed from top

    def test_crop_image_left_right(self):
        """Test cropping from left and right."""
        service = CropService()
        image = Image.new('RGB', (200, 100), color='white')

        cropped = service.crop_image(
            image,
            crop_left_percent=10.0,
            crop_right_percent=15.0
        )

        # 10% of 200 = 20 from left, 15% of 200 = 30 from right
        assert cropped.size == (150, 100)

    def test_crop_image_asymmetric(self):
        """Test asymmetric cropping from all sides."""
        service = CropService()
        image = Image.new('RGB', (100, 100), color='white')

        cropped = service.crop_image(
            image,
            crop_top_percent=5.0,
            crop_bottom_percent=10.0,
            crop_left_percent=15.0,
            crop_right_percent=20.0
        )

        # Width: 100 - 15 - 20 = 65
        # Height: 100 - 5 - 10 = 85
        assert cropped.size == (65, 85)

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
