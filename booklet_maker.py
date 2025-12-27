#!/usr/bin/env python3
"""
Comic Book Booklet Maker

Converts comic book PDFs and CBZ files into print-ready booklet format for 11x17" paper.
Supports page selection, blank page insertion, multiple signatures,
Western/Manga reading order, and duplex/manual printing modes.
"""

import argparse
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Tuple, Union

try:
    from pypdf import PdfReader, PdfWriter, PageObject, Transformation
except ImportError:
    print("Error: pypdf is required. Install with: pip install pypdf")
    sys.exit(1)

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter, landscape
except ImportError:
    print("Error: reportlab is required. Install with: pip install reportlab")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

# PyMuPDF is optional - only needed for split_double_pages
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Import centralized constants
from src.config import (
    IMAGE_EXTENSIONS,
    PAPER_SIZES,
    DEFAULT_PAPER_SIZE,
    SPLIT_WIDTH_MULTIPLIER
)

# DEPRECATED: Constants have been moved to src.config for better maintainability.
# The following imports maintain backward compatibility for any code that imports from this module.
# Please update your imports to use: from src.config import PAPER_SIZES, etc.


def cbz_to_pdf(cbz_path: str) -> str:
    """
    Convert a CBZ file to a temporary PDF.

    CBZ files are ZIP archives containing comic book images.
    This function extracts the images and creates a PDF with one page per image.

    Args:
        cbz_path: Path to the CBZ file

    Returns:
        Path to the temporary PDF file
    """
    cbz_path = Path(cbz_path)

    # Create temporary PDF file
    temp_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    temp_pdf_path = temp_pdf.name
    temp_pdf.close()

    with zipfile.ZipFile(cbz_path, 'r') as zf:
        # Get list of image files, sorted by name
        image_files = sorted([
            name for name in zf.namelist()
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS
            and not Path(name).name.startswith('.')  # Skip hidden files
        ])

        if not image_files:
            raise ValueError(f"No images found in CBZ file: {cbz_path}")

        # Convert images to PDF
        pdf_images = []
        for img_name in image_files:
            with zf.open(img_name) as img_file:
                img = Image.open(img_file)
                # Convert to RGB if necessary (for PNG with transparency, etc.)
                if img.mode in ('RGBA', 'P', 'LA'):
                    # Create white background for transparent images
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                pdf_images.append(img.copy())

        # Save all images as a PDF
        if pdf_images:
            pdf_images[0].save(
                temp_pdf_path,
                'PDF',
                save_all=True,
                append_images=pdf_images[1:] if len(pdf_images) > 1 else []
            )

    print(f"Converted CBZ to temporary PDF: {len(pdf_images)} pages")
    return temp_pdf_path


def split_double_pages(input_path: str, output_path: str = None) -> dict:
    """
    Split double-page spreads in a PDF into separate pages.

    Detects oversized pages (width > 1.5× the most common page width) and splits them
    into left and right halves.

    Args:
        input_path: Path to input PDF file
        output_path: Path for output PDF (if None, creates a temp file)

    Returns:
        dict with: original_pages, output_pages, splits_made, output_path

    Raises:
        RuntimeError: If PyMuPDF is not installed
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF is required for split_double_pages. Install with: pip install pymupdf")

    from collections import Counter

    # Create output path if not provided
    if output_path is None:
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        output_path = temp_file.name
        temp_file.close()

    doc = fitz.open(input_path)
    new_doc = fitz.open()  # Create empty document

    splits_made = 0
    split_pairs = []  # Track which output pages are split pairs
    output_page_num = 0  # Track current output page number
    original_pages = len(doc)

    # Find the most common page width (standard width)
    widths = [round(page.rect.width) for page in doc]
    width_counts = Counter(widths)
    standard_width = width_counts.most_common(1)[0][0]

    for page_num in range(len(doc)):
        page = doc[page_num]
        rect = page.rect
        width = rect.width
        height = rect.height

        # Detect double-page spread: width > threshold× standard width
        if width > standard_width * SPLIT_WIDTH_MULTIPLIER:
            # This is a double-page spread - split it
            splits_made += 1

            # Record the split pair (1-indexed for user-facing page numbers)
            split_pairs.append((output_page_num + 1, output_page_num + 2))

            # Left half
            left_rect = fitz.Rect(0, 0, width / 2, height)
            left_page = new_doc.new_page(width=width / 2, height=height)
            left_page.show_pdf_page(left_page.rect, doc, page_num, clip=left_rect)

            # Right half
            right_rect = fitz.Rect(width / 2, 0, width, height)
            right_page = new_doc.new_page(width=width / 2, height=height)
            right_page.show_pdf_page(right_page.rect, doc, page_num, clip=right_rect)

            # Increment by 2 since we added two pages
            output_page_num += 2
        else:
            # Normal page - copy as-is
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            # Increment by 1 for normal page
            output_page_num += 1

    # Save the new document
    new_doc.save(output_path, garbage=4, deflate=True)
    new_doc.close()
    doc.close()

    return {
        'original_pages': original_pages,
        'output_pages': original_pages + splits_made,
        'splits_made': splits_made,
        'split_pairs': split_pairs,
        'output_path': output_path
    }


# DEPRECATED: PAPER_SIZES and DEFAULT_PAPER_SIZE have been moved to src.config
# They are now imported above for backward compatibility

# Legacy constants for backwards compatibility
SHEET_WIDTH = PAPER_SIZES[DEFAULT_PAPER_SIZE][0]
SHEET_HEIGHT = PAPER_SIZES[DEFAULT_PAPER_SIZE][1]
HALF_WIDTH = SHEET_WIDTH / 2


def parse_page_selection(selection_str: str, total_pages: int) -> List[Union[int, str]]:
    """
    Parse page selection string into a list of page numbers and blank markers.

    Args:
        selection_str: Page selection string (e.g., "b,1-20,b" or "1-10,15,20-25")
        total_pages: Total number of pages in the source PDF

    Returns:
        List of page numbers (1-indexed) and "blank" markers

    Examples:
        "1-5" -> [1, 2, 3, 4, 5]
        "b,1-3,b" -> ["blank", 1, 2, 3, "blank"]
        "1,3,5-7" -> [1, 3, 5, 6, 7]
    """
    result = []
    parts = selection_str.split(',')

    for part in parts:
        part = part.strip().lower()

        if part == 'b' or part == 'blank':
            result.append("blank")
        elif '-' in part:
            # Range of pages
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())

                if start < 1 or end > total_pages:
                    print(f"Warning: Page range {start}-{end} adjusted to fit within 1-{total_pages}")
                    start = max(1, start)
                    end = min(total_pages, end)

                result.extend(range(start, end + 1))
            except ValueError:
                print(f"Warning: Invalid range '{part}', skipping")
        else:
            # Single page number
            try:
                page_num = int(part)
                if 1 <= page_num <= total_pages:
                    result.append(page_num)
                else:
                    print(f"Warning: Page {page_num} out of range (1-{total_pages}), skipping")
            except ValueError:
                print(f"Warning: Invalid page number '{part}', skipping")

    return result


def calculate_booklet_order(pages: List[Union[int, str]], num_signatures: int, reading_order: str) -> List[List[Tuple]]:
    """
    Calculate the imposition order for booklet printing.

    Args:
        pages: List of page numbers and "blank" markers
        num_signatures: Number of signatures to divide the booklet into
        reading_order: "western" (L-to-R) or "manga" (R-to-L)

    Returns:
        List of signatures, each containing list of sheets.
        Each sheet is a tuple: (front_left, front_right, back_left, back_right)
    """
    total_pages = len(pages)

    # Calculate pages per signature (must be multiple of 4)
    pages_per_sig = total_pages // num_signatures
    remainder = total_pages % num_signatures

    # Distribute pages across signatures
    signature_sizes = []
    for i in range(num_signatures):
        size = pages_per_sig + (1 if i < remainder else 0)
        # Round up to multiple of 4
        size = ((size + 3) // 4) * 4
        signature_sizes.append(size)

    # Pad the page list with blanks to match total signature size
    total_needed = sum(signature_sizes)
    padded_pages = pages.copy()
    while len(padded_pages) < total_needed:
        padded_pages.append("blank")

    # Generate imposition for each signature
    all_signatures = []
    page_offset = 0

    for sig_idx, sig_size in enumerate(signature_sizes):
        sig_pages = padded_pages[page_offset:page_offset + sig_size]
        page_offset += sig_size

        sheets = []
        num_sheets = sig_size // 4

        for sheet_idx in range(num_sheets):
            # Standard booklet imposition:
            # Front: [last - 2*i, first + 2*i + 1]
            # Back: [first + 2*i + 2, last - 2*i - 1]
            n = sig_size
            i = sheet_idx

            front_left_idx = n - 1 - (2 * i)
            front_right_idx = 2 * i
            back_left_idx = 2 * i + 1
            back_right_idx = n - 2 - (2 * i)

            front_left = sig_pages[front_left_idx]
            front_right = sig_pages[front_right_idx]
            back_left = sig_pages[back_left_idx]
            back_right = sig_pages[back_right_idx]

            # Swap left/right for manga reading order
            if reading_order == 'manga':
                front_left, front_right = front_right, front_left
                back_left, back_right = back_right, back_left

            sheets.append((front_left, front_right, back_left, back_right))

        all_signatures.append(sheets)

    return all_signatures


def create_blank_page_pdf(width: float, height: float) -> bytes:
    """
    Create a blank white PDF page.

    Args:
        width: Page width in points
        height: Page height in points

    Returns:
        PDF bytes for a blank page
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFillColorRGB(1, 1, 1)  # White
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def get_page_object(reader: PdfReader, page_ref: Union[int, str], blank_width: float, blank_height: float) -> PageObject:
    """
    Get a page object from the reader or create a blank page.

    Args:
        reader: PdfReader instance
        page_ref: Page number (1-indexed) or "blank"
        blank_width: Width for blank pages
        blank_height: Height for blank pages

    Returns:
        PageObject for the requested page
    """
    if page_ref == "blank":
        blank_pdf = create_blank_page_pdf(blank_width, blank_height)
        blank_reader = PdfReader(io.BytesIO(blank_pdf))
        return blank_reader.pages[0]
    else:
        # Convert from 1-indexed to 0-indexed
        return reader.pages[page_ref - 1]


def compose_sheet(left_page: PageObject, right_page: PageObject, paper_size: str = DEFAULT_PAPER_SIZE) -> PageObject:
    """
    Compose two pages side-by-side on a sheet.

    Args:
        left_page: Page to place on left half
        right_page: Page to place on right half
        paper_size: Paper size key from PAPER_SIZES dict

    Returns:
        Composed page at specified paper size
    """
    # Get paper dimensions
    sheet_width, sheet_height = PAPER_SIZES.get(paper_size, PAPER_SIZES[DEFAULT_PAPER_SIZE])
    half_width = sheet_width / 2

    # Create a new blank sheet (landscape)
    sheet = PageObject.create_blank_page(width=sheet_width, height=sheet_height)

    # Get dimensions of source pages
    left_box = left_page.mediabox
    left_w = float(left_box.width)
    left_h = float(left_box.height)

    right_box = right_page.mediabox
    right_w = float(right_box.width)
    right_h = float(right_box.height)

    # Calculate scale and position for left page
    # Scale to fit in half sheet
    left_scale_w = half_width / left_w
    left_scale_h = sheet_height / left_h
    left_scale = min(left_scale_w, left_scale_h)

    left_scaled_w = left_w * left_scale
    left_scaled_h = left_h * left_scale

    # Align right edge to center (no gutter)
    left_x = half_width - left_scaled_w
    left_y = (sheet_height - left_scaled_h) / 2

    # Calculate scale and position for right page
    right_scale_w = half_width / right_w
    right_scale_h = sheet_height / right_h
    right_scale = min(right_scale_w, right_scale_h)

    right_scaled_w = right_w * right_scale
    right_scaled_h = right_h * right_scale

    # Align left edge to center (no gutter)
    right_x = half_width
    right_y = (sheet_height - right_scaled_h) / 2

    # Merge pages onto sheet
    # Apply transformation: scale then translate
    left_transform = Transformation().scale(left_scale, left_scale).translate(left_x, left_y)
    right_transform = Transformation().scale(right_scale, right_scale).translate(right_x, right_y)

    sheet.merge_transformed_page(left_page, left_transform)
    sheet.merge_transformed_page(right_page, right_transform)

    return sheet


def generate_single_booklet(
    reader: PdfReader,
    page_selection: str,
    total_pages: int,
    reading_order: str,
    num_signatures: int,
    duplex_mode: str,
    output_dir: Path,
    output_name: str,
    book_suffix: str = "",
    paper_size: str = DEFAULT_PAPER_SIZE
) -> List[str]:
    """
    Generate a single booklet PDF(s) from page selection.

    Args:
        reader: PdfReader instance
        page_selection: Page selection string
        total_pages: Total pages in source PDF
        reading_order: "western" or "manga"
        num_signatures: Number of signatures
        duplex_mode: "auto" or "manual"
        output_dir: Output directory path
        output_name: Base output name
        book_suffix: Suffix for multiple books (e.g., "_book1")
        paper_size: Paper size key from PAPER_SIZES dict

    Returns:
        List of output file paths
    """
    # Parse page selection
    pages = parse_page_selection(page_selection, total_pages)
    print(f"  Pages: {len(pages)} (including blanks)")

    # Calculate booklet order
    signatures = calculate_booklet_order(pages, num_signatures, reading_order)

    total_sheets = sum(len(sig) for sig in signatures)
    print(f"  Signatures: {len(signatures)}, Sheets: {total_sheets}")

    # Get reference dimensions from first actual page
    ref_page = None
    for p in pages:
        if p != "blank":
            ref_page = reader.pages[p - 1]
            break

    if ref_page is None:
        blank_width, blank_height = letter
    else:
        box = ref_page.mediabox
        blank_width = float(box.width)
        blank_height = float(box.height)

    # Generate sheets
    front_sheets = []
    back_sheets = []

    for sig_idx, sig_sheets in enumerate(signatures):
        for sheet_idx, (front_left, front_right, back_left, back_right) in enumerate(sig_sheets):
            fl_page = get_page_object(reader, front_left, blank_width, blank_height)
            fr_page = get_page_object(reader, front_right, blank_width, blank_height)
            bl_page = get_page_object(reader, back_left, blank_width, blank_height)
            br_page = get_page_object(reader, back_right, blank_width, blank_height)

            front_sheet = compose_sheet(fl_page, fr_page, paper_size)
            back_sheet = compose_sheet(bl_page, br_page, paper_size)

            front_sheets.append(front_sheet)
            back_sheets.append(back_sheet)

    output_files = []
    base_name = f"{output_name}{book_suffix}"

    if duplex_mode == "auto":
        writer = PdfWriter()
        for front, back in zip(front_sheets, back_sheets):
            writer.add_page(front)
            writer.add_page(back)

        output_path = output_dir / f"{base_name}_duplex.pdf"
        with open(output_path, "wb") as f:
            writer.write(f)

        output_files.append(str(output_path))
        print(f"  Created: {output_path.name}")

    else:  # manual
        front_writer = PdfWriter()
        back_writer = PdfWriter()

        for front in front_sheets:
            front_writer.add_page(front)

        for back in back_sheets:
            back_writer.add_page(back)

        front_path = output_dir / f"{base_name}_front.pdf"
        back_path = output_dir / f"{base_name}_back.pdf"

        with open(front_path, "wb") as f:
            front_writer.write(f)

        with open(back_path, "wb") as f:
            back_writer.write(f)

        output_files.extend([str(front_path), str(back_path)])
        print(f"  Created: {front_path.name}")
        print(f"  Created: {back_path.name}")

    return output_files


def generate_booklet(
    input_path: str,
    page_selections: List[str],
    reading_order: str,
    num_signatures: int,
    duplex_mode: str,
    output_name: str = None,
    paper_size: str = DEFAULT_PAPER_SIZE,
    output_dir: str = None
) -> List[str]:
    """
    Generate booklet PDF(s) from input comic PDF.

    Args:
        input_path: Path to input PDF file
        page_selections: List of page selection strings (one per book)
        reading_order: "western" or "manga"
        num_signatures: Number of signatures per book
        duplex_mode: "auto" or "manual"
        output_name: Custom output folder name (default: input filename)
        paper_size: Paper size key from PAPER_SIZES dict
        output_dir: Custom output directory path (default: input_path.parent/prints/output_name)

    Returns:
        List of output file paths
    """
    input_path = Path(input_path)
    temp_pdf_path = None

    # Check if input is a CBZ file and convert to PDF
    if input_path.suffix.lower() == '.cbz':
        print(f"Input CBZ: {input_path.name}")
        temp_pdf_path = cbz_to_pdf(str(input_path))
        pdf_path = temp_pdf_path
    else:
        pdf_path = str(input_path)
        print(f"Input PDF: {input_path.name}")

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        print(f"Total pages: {total_pages}")

        # Default to all pages if no selections provided
        if not page_selections:
            page_selections = [f"1-{total_pages}"]

        # Create output directory
        if output_name is None:
            output_name = input_path.stem

        if output_dir:
            output_dir = Path(output_dir) / output_name
        else:
            output_dir = input_path.parent / "prints" / output_name
        output_dir.mkdir(parents=True, exist_ok=True)

        all_output_files = []
        num_books = len(page_selections)

        print(f"\nGenerating {num_books} booklet(s)...\n")

        for book_idx, page_selection in enumerate(page_selections):
            # Add book suffix only if multiple books
            if num_books > 1:
                book_suffix = f"_book{book_idx + 1}"
                print(f"Book {book_idx + 1}: {page_selection}")
            else:
                book_suffix = ""
                print(f"Selection: {page_selection}")

            output_files = generate_single_booklet(
                reader=reader,
                page_selection=page_selection,
                total_pages=total_pages,
                reading_order=reading_order,
                num_signatures=num_signatures,
                duplex_mode=duplex_mode,
                output_dir=output_dir,
                output_name=output_name,
                book_suffix=book_suffix,
                paper_size=paper_size
            )
            all_output_files.extend(output_files)
            print()

        return all_output_files

    finally:
        # Clean up temporary PDF if we converted from CBZ
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)


def interactive_mode(input_path: str = None) -> dict:
    """
    Gather options interactively from user input.

    Args:
        input_path: Optional pre-specified input path

    Returns:
        Dictionary of options
    """
    print("\n=== Comic Book Booklet Maker ===\n")

    # Input file
    if not input_path:
        input_path = input("Enter path to PDF or CBZ file: ").strip()
        if input_path.startswith('"') and input_path.endswith('"'):
            input_path = input_path[1:-1]

    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    # Get page count (convert CBZ to temp PDF if needed)
    input_path_obj = Path(input_path)
    temp_pdf_for_count = None
    try:
        if input_path_obj.suffix.lower() == '.cbz':
            print("Converting CBZ to get page count...")
            temp_pdf_for_count = cbz_to_pdf(input_path)
            reader = PdfReader(temp_pdf_for_count)
        else:
            reader = PdfReader(input_path)
        total_pages = len(reader.pages)
    finally:
        if temp_pdf_for_count and os.path.exists(temp_pdf_for_count):
            os.unlink(temp_pdf_for_count)

    file_type = "CBZ" if input_path_obj.suffix.lower() == '.cbz' else "PDF"
    print(f"\n{file_type} has {total_pages} pages.\n")

    # Page selections (multiple books)
    print("Page selection examples:")
    print("  - '1-20' for pages 1 through 20")
    print("  - 'b,1-20,b' for blank + pages 1-20 + blank")
    print("  - '1-10,15,20-25' for mixed ranges")
    print("\nYou can create multiple booklets by entering selections one at a time.")
    print("Press Enter with no input when done (or on first prompt for all pages).\n")

    page_selections = []
    book_num = 1
    while True:
        prompt = f"Book {book_num} page selection (empty to finish): "
        selection = input(prompt).strip()

        if not selection:
            if not page_selections:
                # No selections yet, default to all pages
                page_selections = [f"1-{total_pages}"]
            break

        page_selections.append(selection)
        book_num += 1

    print(f"\n{len(page_selections)} booklet(s) will be created.")

    # Reading order
    print("\nReading order:")
    print("  1. Western (left-to-right)")
    print("  2. Manga (right-to-left)")
    order_choice = input("Choose [1]: ").strip()
    reading_order = "manga" if order_choice == "2" else "western"

    # Signatures
    sig_input = input("\nNumber of signatures per book [1]: ").strip()
    try:
        num_signatures = int(sig_input) if sig_input else 1
        num_signatures = max(1, num_signatures)
    except ValueError:
        num_signatures = 1

    # Duplex mode
    print("\nDuplex mode:")
    print("  1. Auto (single PDF for duplex printers)")
    print("  2. Manual (two PDFs for manual flipping)")
    duplex_choice = input("Choose [1]: ").strip()
    duplex_mode = "manual" if duplex_choice == "2" else "auto"

    # Output name
    default_name = Path(input_path).stem
    output_name = input(f"\nOutput folder name [{default_name}]: ").strip()
    if not output_name:
        output_name = default_name

    return {
        'input_path': input_path,
        'page_selections': page_selections,
        'reading_order': reading_order,
        'num_signatures': num_signatures,
        'duplex_mode': duplex_mode,
        'output_name': output_name
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert comic PDFs and CBZ files to print-ready booklet format. Supports multiple paper sizes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s comic.pdf
  %(prog)s comic.cbz                                   # CBZ files supported
  %(prog)s comic.pdf -p "1-20"
  %(prog)s comic.pdf -p "1-24" -p "25-48" -p "49-72"   # Multiple books
  %(prog)s comic.pdf -p "b,1-20,b" --reading-order manga
  %(prog)s comic.pdf -p "1-48" --signatures 2 --duplex manual
  %(prog)s comic.pdf -p "1-20" --paper-size letter    # Use letter size paper
        """
    )

    parser.add_argument('input', nargs='?', help='Input PDF or CBZ file')
    parser.add_argument('-p', '--pages', action='append',
                        help='Page selection (can be used multiple times for multiple books)')
    parser.add_argument('--reading-order', choices=['western', 'manga'], default='western',
                        help='Reading order: western (L-to-R) or manga (R-to-L)')
    parser.add_argument('--signatures', type=int, default=1,
                        help='Number of signatures per book (default: 1)')
    parser.add_argument('--duplex', choices=['auto', 'manual'], default='auto',
                        help='Duplex mode: auto (single PDF) or manual (two PDFs)')
    parser.add_argument('--output-name', help='Custom output folder name')
    parser.add_argument('--paper-size', choices=list(PAPER_SIZES.keys()), default=DEFAULT_PAPER_SIZE,
                        help=f'Paper size: {", ".join(PAPER_SIZES.keys())} (default: {DEFAULT_PAPER_SIZE})')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Force interactive mode')

    args = parser.parse_args()

    # Determine if we need interactive mode
    if args.interactive or args.input is None:
        options = interactive_mode(args.input)
    else:
        options = {
            'input_path': args.input,
            'page_selections': args.pages if args.pages else [],
            'reading_order': args.reading_order,
            'num_signatures': args.signatures,
            'duplex_mode': args.duplex,
            'output_name': args.output_name,
            'paper_size': args.paper_size
        }

    # Generate the booklet
    try:
        output_files = generate_booklet(**options)
        print(f"\nBooklet generation complete!")
        print(f"Output files: {len(output_files)}")
        for f in output_files:
            print(f"  - {f}")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
