#!/usr/bin/env python3
"""
Booklet Maker GUI

A visual interface for selecting pages and creating print-ready booklets.
Uses booklet_maker.py as the backend for PDF generation.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Optional, Tuple
import threading

try:
    import pypdfium2 as pdfium
except ImportError:
    print("Error: pypdfium2 is required. Install with: pip install pypdfium2")
    sys.exit(1)

try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

# Import booklet_maker for generation
try:
    from booklet_maker import (
        generate_booklet, parse_page_selection, calculate_booklet_order,
        PAPER_SIZES, DEFAULT_PAPER_SIZE, cbz_to_pdf,
        split_double_pages, PYMUPDF_AVAILABLE
    )
except ImportError:
    print("Error: booklet_maker.py must be in the same directory")
    sys.exit(1)

# Import centralized UI configuration
from src.config import UITheme, THUMBNAIL_SIZE, PREVIEW_SIZE, GRID_COLUMNS

# Import validators for business logic
from src.validators import SpreadValidator
from src.models import SpreadPair

import json

# Configuration file handling
DEFAULT_CONFIG = {
    "reading_order": "western",
    "signatures": 1,
    "duplex_mode": "auto",
    "paper_size": DEFAULT_PAPER_SIZE,
    "output_folder": "",
    "default_crop": {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
}

def get_config_path() -> Path:
    """Get path to config file in same directory as script."""
    return Path(__file__).parent / "config.json"

def load_config() -> dict:
    """Load config from file, return defaults if not found."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                saved_config = json.load(f)
                # Merge with defaults to handle missing keys
                config = DEFAULT_CONFIG.copy()
                config.update(saved_config)

                # Migration: Convert old single-value crop to new 4-sided format
                if 'default_crop_percent' in config and 'default_crop' not in saved_config:
                    old_value = config.pop('default_crop_percent', 0.0)
                    config['default_crop'] = {
                        'top': 0.0,
                        'bottom': old_value,
                        'left': 0.0,
                        'right': 0.0
                    }
                elif 'default_crop_percent' in config:
                    # Remove old key if new format is present
                    config.pop('default_crop_percent', None)

                return config
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config: dict) -> None:
    """Save config dict to file."""
    config_path = get_config_path()
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    except IOError:
        pass  # Silently fail if can't write config


class ThumbnailCache:
    """Manages PDF page thumbnails with lazy loading."""

    def __init__(self, pdf_path: str, thumb_size: Tuple[int, int] = THUMBNAIL_SIZE):
        self.pdf_path = pdf_path
        self.thumb_size = thumb_size
        self.pdf = pdfium.PdfDocument(pdf_path)
        self.total_pages = len(self.pdf)
        self._cache = {}
        self._loading = set()

    def get_thumbnail(self, page_num: int) -> Optional[Image.Image]:
        """Get thumbnail for page (1-indexed). Returns None if not yet loaded."""
        if page_num in self._cache:
            return self._cache[page_num]
        return None

    def load_thumbnail(self, page_num: int) -> Image.Image:
        """Load and cache thumbnail for page (1-indexed)."""
        if page_num in self._cache:
            return self._cache[page_num]

        page = self.pdf[page_num - 1]
        # Calculate scale to fit thumb_size while maintaining aspect ratio
        page_width = page.get_width()
        page_height = page.get_height()
        scale_w = self.thumb_size[0] / page_width
        scale_h = self.thumb_size[1] / page_height
        scale = min(scale_w, scale_h)

        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()

        # Ensure consistent size with padding
        result = Image.new('RGB', self.thumb_size, 'white')
        x = (self.thumb_size[0] - pil_image.width) // 2
        y = (self.thumb_size[1] - pil_image.height) // 2
        result.paste(pil_image, (x, y))

        self._cache[page_num] = result
        return result

    def load_all(self, callback=None):
        """Load all thumbnails. Calls callback(page_num) after each load."""
        for i in range(1, self.total_pages + 1):
            self.load_thumbnail(i)
            if callback:
                callback(i)

    def close(self):
        """Close the PDF document."""
        self.pdf.close()


class ThumbnailGrid(ttk.Frame):
    """Scrollable grid of page thumbnails with selection support."""

    def __init__(self, parent, on_selection_change=None, on_spread_change=None, on_hover=None, theme: UITheme = None, default_crop: dict = None):
        super().__init__(parent)
        self.on_selection_change = on_selection_change
        self.on_spread_change = on_spread_change
        self.on_hover = on_hover
        self.theme = theme or UITheme()  # Use provided theme or default
        self.cache: Optional[ThumbnailCache] = None
        self.photo_images = {}  # Keep references to prevent GC
        self.selected_pages = []  # Ordered list of selected page numbers
        self.thumb_labels = {}  # page_num -> label widget
        self.columns = GRID_COLUMNS  # Use centralized grid column count

        # Spread tracking
        self.spread_pairs = []  # List of (page1, page2) tuples for double-page spreads
        self.pending_spread_page = None  # First page of incomplete spread marking

        # Crop tracking - now supports 4-sided crops
        self.page_crops = {}  # {page_num: {'top': x, 'bottom': y, 'left': z, 'right': w}}
        self.default_crop = default_crop or {'top': 0.0, 'bottom': 0.0, 'left': 0.0, 'right': 0.0}

        # Create scrollable canvas
        self.canvas = tk.Canvas(self, bg='#f0f0f0')
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Bind mouse wheel
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_canvas_resize(self, event):
        # Update columns based on width
        new_cols = max(1, event.width // 120)
        if new_cols != self.columns and self.cache:
            self.columns = new_cols
            self._rebuild_grid()

    def load_pdf(self, pdf_path: str, progress_callback=None):
        """Load a PDF and create thumbnails."""
        if self.cache:
            self.cache.close()

        self.cache = ThumbnailCache(pdf_path)
        self.selected_pages = []
        self.spread_pairs = []
        self.photo_images = {}
        self.thumb_labels = {}

        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # Load thumbnails
        def load_and_display():
            for i in range(1, self.cache.total_pages + 1):
                self.cache.load_thumbnail(i)
                self.after(0, lambda p=i: self._add_thumbnail(p))
                if progress_callback:
                    progress_callback(i, self.cache.total_pages)

        threading.Thread(target=load_and_display, daemon=True).start()

    def _add_thumbnail(self, page_num: int):
        """Add a single thumbnail to the grid."""
        thumb = self.cache.get_thumbnail(page_num)
        if thumb is None:
            return

        # Create frame for thumbnail + label
        frame = ttk.Frame(self.scrollable_frame)
        row = (page_num - 1) // self.columns
        col = (page_num - 1) % self.columns
        frame.grid(row=row, column=col, padx=4, pady=4)

        # Convert to PhotoImage
        photo = ImageTk.PhotoImage(thumb)
        self.photo_images[page_num] = photo

        # Create label with image
        label = tk.Label(frame, image=photo, bd=3, relief="flat", bg='#f0f0f0')
        label.pack()
        label.bind("<Button-1>", lambda e, p=page_num: self._on_click(p, e))
        label.bind("<Shift-Button-1>", lambda e, p=page_num: self._on_shift_click(p, e))
        label.bind("<Control-Button-1>", lambda e, p=page_num: self._on_ctrl_click(p, e))
        label.bind("<Enter>", lambda e, p=page_num: self._on_hover(p))
        label.bind("<Button-3>", lambda e, p=page_num: self._on_right_click(p, e))  # Right-click menu
        label.bind("<Control-Button-3>", lambda e, p=page_num: self._on_ctrl_right_click(p, e))  # Quick apply default trim

        # Page number label
        num_label = ttk.Label(frame, text=str(page_num))
        num_label.pack()

        self.thumb_labels[page_num] = label

        # Apply spread highlighting immediately if this page is in a spread pair
        if self._is_page_in_spread(page_num):
            label.configure(
                highlightbackground=self.theme.color_spread,
                highlightthickness=self.theme.highlight_thickness
            )

    def _is_page_in_spread(self, page_num: int) -> bool:
        """Check if a page is part of any spread pair."""
        for p1, p2 in self.spread_pairs:
            if page_num == p1 or page_num == p2:
                return True
        return False

    def _rebuild_grid(self):
        """Rebuild the grid layout with current column count."""
        for page_num, label in self.thumb_labels.items():
            frame = label.master
            row = (page_num - 1) // self.columns
            col = (page_num - 1) % self.columns
            frame.grid(row=row, column=col, padx=4, pady=4)

    def _on_click(self, page_num: int, event):
        """Handle single click - add page to selection."""
        # Check for modifier keys (fallback for Windows where bindings may not work)
        if event.state & 0x4:  # Ctrl key
            return self._on_ctrl_click(page_num, event)
        if event.state & 0x1:  # Shift key
            return self._on_shift_click(page_num, event)

        if page_num in self.selected_pages:
            # If already selected, add another instance (for repeats)
            self.selected_pages.append(page_num)
        else:
            self.selected_pages.append(page_num)
        self._update_selection_display()
        if self.on_selection_change:
            self.on_selection_change(self.selected_pages)

    def _on_shift_click(self, page_num: int, event):
        """Handle shift+click - select range from last selected."""
        if not self.selected_pages:
            self.selected_pages.append(page_num)
        else:
            last = self.selected_pages[-1]
            if last <= page_num:
                for p in range(last + 1, page_num + 1):
                    self.selected_pages.append(p)
            else:
                for p in range(last - 1, page_num - 1, -1):
                    self.selected_pages.append(p)
        self._update_selection_display()
        if self.on_selection_change:
            self.on_selection_change(self.selected_pages)

    def _on_ctrl_click(self, page_num: int, event):
        """Handle ctrl+click - mark double-page spreads."""
        if self.pending_spread_page is None:
            # First page of spread pair
            self.pending_spread_page = page_num
            self._update_selection_display()
        else:
            # Second page of spread pair
            first_page = self.pending_spread_page
            second_page = page_num

            # Check if pages are adjacent
            if abs(first_page - second_page) == 1:
                # Order the pair (lower page first)
                pair = (min(first_page, second_page), max(first_page, second_page))

                # Check if already marked as spread
                if pair in self.spread_pairs:
                    # Remove the spread pair
                    self.spread_pairs.remove(pair)
                else:
                    # Add as spread pair
                    self.spread_pairs.append(pair)

                self.pending_spread_page = None
                self._update_selection_display()
                # Notify about spread change
                if self.on_spread_change:
                    self.on_spread_change(self.spread_pairs)
            else:
                # Not adjacent - show error and reset
                messagebox.showwarning("Invalid Spread",
                    f"Pages {first_page} and {second_page} are not adjacent.\n"
                    "Double-page spreads must be consecutive pages.")
                self.pending_spread_page = None
                self._update_selection_display()

    def _on_hover(self, page_num: int):
        """Handle mouse hover over a thumbnail."""
        if self.on_hover:
            self.on_hover(page_num)

    def _on_right_click(self, page_num: int, event):
        """Show context menu on right-click."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Trim...",
            command=lambda: self._show_crop_dialog(page_num)
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_ctrl_right_click(self, page_num: int, event):
        """Quick apply default trim on Ctrl+Right-click."""
        has_default = any(self.default_crop.get(k, 0) > 0 for k in ['top', 'bottom', 'left', 'right'])
        if has_default:
            self._apply_crop(page_num, self.default_crop.copy(), False)

    def _show_crop_dialog(self, page_num: int):
        """Open crop dialog for page."""
        if self.cache is None:
            return

        current_crop = self.page_crops.get(page_num, self.default_crop.copy())

        dialog = CropDialog(
            parent=self.master,
            page_num=page_num,
            pdf_cache=self.cache,
            initial_crops=current_crop,
            default_crops=self.default_crop,
            on_apply=lambda crops, set_default: self._apply_crop(page_num, crops, set_default)
        )

    def _apply_crop(self, page_num: int, crops: dict, set_as_default: bool = False):
        """Store crop data and update visual indicator."""
        has_any_crop = any(crops.get(k, 0) > 0 for k in ['top', 'bottom', 'left', 'right'])

        if has_any_crop:
            self.page_crops[page_num] = crops.copy()

            # Update default if user checked "Set as default"
            if set_as_default:
                self.default_crop = crops.copy()

            # Update thumbnail to show cropped version
            self._update_thumbnail_with_crop(page_num, crops)

            # Add purple border to indicate cropped page
            if page_num in self.thumb_labels:
                self.thumb_labels[page_num].configure(
                    highlightbackground=self.theme.color_crop,
                    highlightthickness=self.theme.highlight_thickness
                )
        else:
            # Remove crop if all values are 0
            self.page_crops.pop(page_num, None)

            # Restore original thumbnail
            self._restore_original_thumbnail(page_num)

            if page_num in self.thumb_labels:
                # Reset to default appearance
                self._update_selection_display()

    def get_page_crops(self) -> dict:
        """Get dictionary of page crops for booklet generation."""
        return self.page_crops.copy()

    def _update_thumbnail_with_crop(self, page_num: int, crops: dict):
        """Update thumbnail to show cropped version."""
        if self.cache is None or page_num not in self.thumb_labels:
            return

        # Get original cached thumbnail
        thumb = self.cache.get_thumbnail(page_num)
        if thumb is None:
            return

        # Apply crop using CropService
        from src.services.crop_service import CropService
        crop_service = CropService()
        cropped_thumb = crop_service.crop_image(
            thumb,
            crop_top_percent=crops.get('top', 0),
            crop_bottom_percent=crops.get('bottom', 0),
            crop_left_percent=crops.get('left', 0),
            crop_right_percent=crops.get('right', 0)
        )

        # Convert to PhotoImage and update label
        photo = ImageTk.PhotoImage(cropped_thumb)
        self.photo_images[page_num] = photo  # Keep reference
        self.thumb_labels[page_num].configure(image=photo)

    def _restore_original_thumbnail(self, page_num: int):
        """Restore original uncropped thumbnail."""
        if self.cache is None or page_num not in self.thumb_labels:
            return

        # Get original cached thumbnail (uncropped)
        thumb = self.cache.get_thumbnail(page_num)
        if thumb is None:
            return

        # Convert to PhotoImage and update label
        photo = ImageTk.PhotoImage(thumb)
        self.photo_images[page_num] = photo  # Keep reference
        self.thumb_labels[page_num].configure(image=photo)

    def _update_selection_display(self):
        """Update visual indication of selected pages."""
        # Count occurrences of each page
        counts = {}
        for p in self.selected_pages:
            counts[p] = counts.get(p, 0) + 1

        # Collect spread pages for yellow highlighting
        spread_pages = set()
        for p1, p2 in self.spread_pairs:
            spread_pages.add(p1)
            spread_pages.add(p2)

        for page_num, label in self.thumb_labels.items():
            if page_num == self.pending_spread_page:
                # Pending spread page - orange to indicate waiting for second page
                label.configure(
                    highlightbackground=self.theme.color_pending,
                    highlightthickness=self.theme.highlight_thickness
                )
            elif page_num in spread_pages:
                # Spread pair - yellow
                label.configure(
                    highlightbackground=self.theme.color_spread,
                    highlightthickness=self.theme.highlight_thickness
                )
            elif page_num in counts:
                # Selected - green
                label.configure(
                    highlightbackground=self.theme.color_selected,
                    highlightthickness=self.theme.highlight_thickness
                )
            else:
                # Not selected
                label.configure(highlightbackground='#f0f0f0', highlightthickness=0)

    def set_selection(self, pages: List[int]):
        """Set selection from list of page numbers."""
        self.selected_pages = pages.copy()
        self._update_selection_display()

    def clear_selection(self):
        """Clear all selections."""
        self.selected_pages = []
        self._update_selection_display()
        if self.on_selection_change:
            self.on_selection_change(self.selected_pages)

    def get_spread_pairs(self) -> List[Tuple[int, int]]:
        """Get the list of marked spread pairs."""
        return self.spread_pairs.copy()

    def check_spread_alignment(self, pages: List) -> List[Tuple[Tuple[int, int], int, int]]:
        """
        Check if marked spreads will print correctly aligned.

        NOTE: This method now delegates to SpreadValidator for testable business logic.

        Args:
            pages: List of page numbers/blanks in selection order

        Returns:
            List of (spread_pair, pos1, pos2) for misaligned spreads
        """
        # Convert tuples to SpreadPair objects for validation
        spread_objects = [SpreadPair(p1, p2) for p1, p2 in self.spread_pairs]

        # Use validator for business logic (testable!)
        results = SpreadValidator.check_spread_alignment(pages, spread_objects)

        # Filter to only misaligned spreads and convert back to expected format
        misaligned = []
        for spread, pos1, pos2, is_aligned in results:
            if not is_aligned:
                misaligned.append((spread.as_tuple(), pos1, pos2))

        return misaligned


class PagePreview(ttk.Frame):
    """Shows a larger preview of the currently hovered page."""

    # Use centralized preview size from config
    # PREVIEW_SIZE is now imported from src.config

    def __init__(self, parent):
        super().__init__(parent)

        self.cache: Optional[ThumbnailCache] = None
        self.current_page = None
        self.photo_image = None  # Keep reference to prevent GC

        # Header label showing page number
        self.header = ttk.Label(self, text="Hover over a page", font=('TkDefaultFont', 10, 'bold'))
        self.header.pack(pady=(0, 10))

        # Canvas to display the page image
        self.canvas = tk.Canvas(self, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg='#f0f0f0')
        self.canvas.pack(fill='both', expand=True)

        # Create placeholder text
        self.placeholder_text = self.canvas.create_text(
            PREVIEW_SIZE[0] // 2, PREVIEW_SIZE[1] // 2,
            text="Hover over a page\nto preview",
            font=('TkDefaultFont', 12),
            fill='#888888',
            justify='center'
        )
        self.image_id = None

    def set_cache(self, cache: ThumbnailCache):
        """Set the thumbnail cache to use for rendering pages."""
        self.cache = cache
        self.clear()

    def show_page(self, page_num: int, crops: dict = None):
        """Show a larger preview of the specified page."""
        if not self.cache or page_num == self.current_page:
            return

        if page_num < 1 or page_num > self.cache.total_pages:
            return

        self.current_page = page_num
        self.header.configure(text=f"Page {page_num} of {self.cache.total_pages}")

        # Render page at larger size
        try:
            page = self.cache.pdf[page_num - 1]
            page_width = page.get_width()
            page_height = page.get_height()

            # Calculate scale to fit preview size while maintaining aspect ratio
            scale_w = PREVIEW_SIZE[0] / page_width
            scale_h = PREVIEW_SIZE[1] / page_height
            scale = min(scale_w, scale_h)

            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()

            # Apply crop if present
            if crops and any(crops.get(k, 0) > 0 for k in ['top', 'bottom', 'left', 'right']):
                from src.services.crop_service import CropService
                crop_service = CropService()
                pil_image = crop_service.crop_image(
                    pil_image,
                    crop_top_percent=crops.get('top', 0),
                    crop_bottom_percent=crops.get('bottom', 0),
                    crop_left_percent=crops.get('left', 0),
                    crop_right_percent=crops.get('right', 0)
                )

            # Center the image in the preview area
            result = Image.new('RGB', PREVIEW_SIZE, '#f0f0f0')
            x = (PREVIEW_SIZE[0] - pil_image.width) // 2
            y = (PREVIEW_SIZE[1] - pil_image.height) // 2
            result.paste(pil_image, (x, y))

            # Convert to PhotoImage and display
            self.photo_image = ImageTk.PhotoImage(result)

            # Hide placeholder, show image
            self.canvas.itemconfigure(self.placeholder_text, state='hidden')

            if self.image_id:
                self.canvas.itemconfigure(self.image_id, image=self.photo_image, state='normal')
            else:
                self.image_id = self.canvas.create_image(0, 0, anchor='nw', image=self.photo_image)

        except Exception as e:
            self.header.configure(text=f"Error loading page {page_num}")

    def clear(self):
        """Clear the preview and show placeholder."""
        self.current_page = None
        self.header.configure(text="Hover over a page")

        # Show placeholder, hide image
        self.canvas.itemconfigure(self.placeholder_text, state='normal')
        if self.image_id:
            self.canvas.itemconfigure(self.image_id, state='hidden')


class CropDialog(tk.Toplevel):
    """Dialog for adjusting page trim with draggable edges on all sides."""

    EDGE_THRESHOLD = 8  # Pixels for edge detection
    EDGE_COLOR = '#9C27B0'  # Purple
    DEFAULT_EDGE_COLOR = '#666666'  # Gray for default indicators
    OVERLAY_COLOR = '#9C27B0'  # Purple for overlay
    CANVAS_WIDTH = 400
    CANVAS_HEIGHT = 500
    CANVAS_PADDING = 20

    def __init__(self, parent, page_num: int, pdf_cache,
                 initial_crops: dict = None, default_crops: dict = None, on_apply=None):
        super().__init__(parent)
        self.title(f"Trim - Page {page_num}")
        self.geometry("460x650")
        self.transient(parent)
        self.grab_set()

        self.page_num = page_num
        self.pdf_cache = pdf_cache
        self.on_apply = on_apply
        self.default_crops = default_crops or {'top': 0.0, 'bottom': 0.0, 'left': 0.0, 'right': 0.0}

        # Initialize crop values
        initial = initial_crops or self.default_crops.copy()
        self.crop_top = tk.DoubleVar(value=initial.get('top', 0.0))
        self.crop_bottom = tk.DoubleVar(value=initial.get('bottom', 0.0))
        self.crop_left = tk.DoubleVar(value=initial.get('left', 0.0))
        self.crop_right = tk.DoubleVar(value=initial.get('right', 0.0))

        # Set as default checkbox
        self.set_as_default = tk.BooleanVar(value=False)

        # Drag state
        self.dragging_edge = None

        # Image positioning (set during _update_preview)
        self.image_x = 0
        self.image_y = 0
        self.image_width = 0
        self.image_height = 0

        # Render original page
        page = pdf_cache.pdf[page_num - 1]
        bitmap = page.render(scale=2.0)
        self.original_image = bitmap.to_pil()

        self._create_ui()
        self._update_preview()

    def _create_ui(self):
        """Create dialog UI with interactive preview canvas."""
        # Main canvas for interactive preview
        canvas_frame = ttk.LabelFrame(self, text="Drag edges to trim")
        canvas_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(canvas_frame, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, bg='#2d2d2d')
        self.canvas.pack(fill='both', expand=True, padx=5, pady=5)

        # Bind mouse events
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Checkbox for default
        self.default_check = ttk.Checkbutton(
            self,
            text="Set as default trim for future pages",
            variable=self.set_as_default
        )
        self.default_check.pack(pady=5)

        # Button frame
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', padx=10, pady=10)

        ttk.Button(btn_frame, text="Reset", command=self._on_reset).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side='right', padx=5)
        ttk.Button(btn_frame, text="Apply", command=self._on_apply_click).pack(side='right', padx=5)

    def _get_edge_positions(self) -> dict:
        """Get current edge positions in canvas coordinates."""
        top_offset = int(self.image_height * self.crop_top.get() / 100)
        bottom_offset = int(self.image_height * self.crop_bottom.get() / 100)
        left_offset = int(self.image_width * self.crop_left.get() / 100)
        right_offset = int(self.image_width * self.crop_right.get() / 100)

        return {
            'top': self.image_y + top_offset,
            'bottom': self.image_y + self.image_height - bottom_offset,
            'left': self.image_x + left_offset,
            'right': self.image_x + self.image_width - right_offset
        }

    def _get_default_edge_positions(self) -> dict:
        """Get default edge positions in canvas coordinates."""
        top_offset = int(self.image_height * self.default_crops.get('top', 0) / 100)
        bottom_offset = int(self.image_height * self.default_crops.get('bottom', 0) / 100)
        left_offset = int(self.image_width * self.default_crops.get('left', 0) / 100)
        right_offset = int(self.image_width * self.default_crops.get('right', 0) / 100)

        return {
            'top': self.image_y + top_offset,
            'bottom': self.image_y + self.image_height - bottom_offset,
            'left': self.image_x + left_offset,
            'right': self.image_x + self.image_width - right_offset
        }

    def _detect_edge(self, x: int, y: int) -> Optional[str]:
        """Detect which edge the mouse is near."""
        edges = self._get_edge_positions()

        # Check horizontal edges (top/bottom)
        if self.image_x <= x <= self.image_x + self.image_width:
            if abs(y - edges['top']) <= self.EDGE_THRESHOLD:
                return 'top'
            if abs(y - edges['bottom']) <= self.EDGE_THRESHOLD:
                return 'bottom'

        # Check vertical edges (left/right)
        if self.image_y <= y <= self.image_y + self.image_height:
            if abs(x - edges['left']) <= self.EDGE_THRESHOLD:
                return 'left'
            if abs(x - edges['right']) <= self.EDGE_THRESHOLD:
                return 'right'

        return None

    def _on_mouse_move(self, event):
        """Update cursor based on edge proximity."""
        edge = self._detect_edge(event.x, event.y)

        if edge in ('top', 'bottom'):
            self.canvas.config(cursor='sb_v_double_arrow')
        elif edge in ('left', 'right'):
            self.canvas.config(cursor='sb_h_double_arrow')
        else:
            self.canvas.config(cursor='')

    def _on_mouse_down(self, event):
        """Start dragging if on an edge."""
        self.dragging_edge = self._detect_edge(event.x, event.y)

    def _on_drag(self, event):
        """Handle drag movement."""
        if not self.dragging_edge:
            return

        edges = self._get_edge_positions()
        min_visible = 0.4  # 40% minimum visible

        if self.dragging_edge == 'top':
            # Constrain: can't go above image top or below (bottom edge - min_height)
            min_pos = self.image_y
            max_pos = edges['bottom'] - int(self.image_height * min_visible)
            new_pos = max(min_pos, min(max_pos, event.y))

            pixel_offset = new_pos - self.image_y
            new_percent = (pixel_offset / self.image_height) * 100
            self.crop_top.set(max(0, min(30, new_percent)))

        elif self.dragging_edge == 'bottom':
            # Constrain: can't go below image bottom or above (top edge + min_height)
            min_pos = edges['top'] + int(self.image_height * min_visible)
            max_pos = self.image_y + self.image_height
            new_pos = max(min_pos, min(max_pos, event.y))

            pixel_offset = (self.image_y + self.image_height) - new_pos
            new_percent = (pixel_offset / self.image_height) * 100
            self.crop_bottom.set(max(0, min(30, new_percent)))

        elif self.dragging_edge == 'left':
            # Constrain: can't go left of image or right of (right edge - min_width)
            min_pos = self.image_x
            max_pos = edges['right'] - int(self.image_width * min_visible)
            new_pos = max(min_pos, min(max_pos, event.x))

            pixel_offset = new_pos - self.image_x
            new_percent = (pixel_offset / self.image_width) * 100
            self.crop_left.set(max(0, min(30, new_percent)))

        elif self.dragging_edge == 'right':
            # Constrain: can't go right of image or left of (left edge + min_width)
            min_pos = edges['left'] + int(self.image_width * min_visible)
            max_pos = self.image_x + self.image_width
            new_pos = max(min_pos, min(max_pos, event.x))

            pixel_offset = (self.image_x + self.image_width) - new_pos
            new_percent = (pixel_offset / self.image_width) * 100
            self.crop_right.set(max(0, min(30, new_percent)))

        self._update_preview()

    def _on_mouse_up(self, event):
        """End dragging."""
        self.dragging_edge = None

    def _on_reset(self):
        """Reset all crops to zero."""
        self.crop_top.set(0)
        self.crop_bottom.set(0)
        self.crop_left.set(0)
        self.crop_right.set(0)
        self._update_preview()

    def _on_apply_click(self):
        """Apply crops and close."""
        if self.on_apply:
            crops = {
                'top': self.crop_top.get(),
                'bottom': self.crop_bottom.get(),
                'left': self.crop_left.get(),
                'right': self.crop_right.get()
            }
            self.on_apply(crops, self.set_as_default.get())
        self.destroy()

    def _update_preview(self):
        """Update the interactive preview with overlays and edges."""
        self.canvas.delete('all')

        # Calculate scaled image size to fit canvas
        canvas_inner_width = self.CANVAS_WIDTH - 2 * self.CANVAS_PADDING
        canvas_inner_height = self.CANVAS_HEIGHT - 2 * self.CANVAS_PADDING

        orig_width, orig_height = self.original_image.size
        scale = min(canvas_inner_width / orig_width, canvas_inner_height / orig_height)

        self.image_width = int(orig_width * scale)
        self.image_height = int(orig_height * scale)
        self.image_x = (self.CANVAS_WIDTH - self.image_width) // 2
        self.image_y = (self.CANVAS_HEIGHT - self.image_height) // 2

        # Create scaled image
        scaled_image = self.original_image.resize(
            (self.image_width, self.image_height),
            Image.Resampling.LANCZOS
        )
        self.photo_image = ImageTk.PhotoImage(scaled_image)
        self.canvas.create_image(self.image_x, self.image_y, anchor='nw', image=self.photo_image)

        # Get edge positions
        edges = self._get_edge_positions()
        default_edges = self._get_default_edge_positions()

        # Draw semi-transparent overlays for cropped regions
        # Top overlay
        if self.crop_top.get() > 0:
            self.canvas.create_rectangle(
                self.image_x, self.image_y,
                self.image_x + self.image_width, edges['top'],
                fill=self.OVERLAY_COLOR, stipple='gray50', outline=''
            )

        # Bottom overlay
        if self.crop_bottom.get() > 0:
            self.canvas.create_rectangle(
                self.image_x, edges['bottom'],
                self.image_x + self.image_width, self.image_y + self.image_height,
                fill=self.OVERLAY_COLOR, stipple='gray50', outline=''
            )

        # Left overlay
        if self.crop_left.get() > 0:
            self.canvas.create_rectangle(
                self.image_x, edges['top'],
                edges['left'], edges['bottom'],
                fill=self.OVERLAY_COLOR, stipple='gray50', outline=''
            )

        # Right overlay
        if self.crop_right.get() > 0:
            self.canvas.create_rectangle(
                edges['right'], edges['top'],
                self.image_x + self.image_width, edges['bottom'],
                fill=self.OVERLAY_COLOR, stipple='gray50', outline=''
            )

        # Draw default edge indicators (dashed lines) if defaults exist
        has_defaults = any(self.default_crops.get(k, 0) > 0 for k in ['top', 'bottom', 'left', 'right'])
        if has_defaults:
            if self.default_crops.get('top', 0) > 0:
                self.canvas.create_line(
                    self.image_x, default_edges['top'],
                    self.image_x + self.image_width, default_edges['top'],
                    fill=self.DEFAULT_EDGE_COLOR, dash=(4, 4), width=2
                )
            if self.default_crops.get('bottom', 0) > 0:
                self.canvas.create_line(
                    self.image_x, default_edges['bottom'],
                    self.image_x + self.image_width, default_edges['bottom'],
                    fill=self.DEFAULT_EDGE_COLOR, dash=(4, 4), width=2
                )
            if self.default_crops.get('left', 0) > 0:
                self.canvas.create_line(
                    default_edges['left'], self.image_y,
                    default_edges['left'], self.image_y + self.image_height,
                    fill=self.DEFAULT_EDGE_COLOR, dash=(4, 4), width=2
                )
            if self.default_crops.get('right', 0) > 0:
                self.canvas.create_line(
                    default_edges['right'], self.image_y,
                    default_edges['right'], self.image_y + self.image_height,
                    fill=self.DEFAULT_EDGE_COLOR, dash=(4, 4), width=2
                )

        # Draw current edge lines (solid, draggable)
        edge_width = 4

        # Top edge
        self.canvas.create_line(
            self.image_x, edges['top'],
            self.image_x + self.image_width, edges['top'],
            fill=self.EDGE_COLOR, width=edge_width
        )

        # Bottom edge
        self.canvas.create_line(
            self.image_x, edges['bottom'],
            self.image_x + self.image_width, edges['bottom'],
            fill=self.EDGE_COLOR, width=edge_width
        )

        # Left edge
        self.canvas.create_line(
            edges['left'], self.image_y,
            edges['left'], self.image_y + self.image_height,
            fill=self.EDGE_COLOR, width=edge_width
        )

        # Right edge
        self.canvas.create_line(
            edges['right'], self.image_y,
            edges['right'], self.image_y + self.image_height,
            fill=self.EDGE_COLOR, width=edge_width
        )


class BookListPanel(ttk.Frame):
    """Panel showing list of saved books with edit/delete controls."""

    def __init__(self, parent, on_select=None, on_delete=None):
        super().__init__(parent)
        self.on_select = on_select
        self.on_delete = on_delete
        self.books = []
        self.current_index = 0

        # Header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill='x', pady=(0, 5))
        ttk.Label(header_frame, text="Books", font=('TkDefaultFont', 10, 'bold')).pack(side='left')
        ttk.Button(header_frame, text="+ New Book", command=self._new_book, width=12).pack(side='right')

        # Book list with scrollbar
        list_frame = ttk.Frame(self)
        list_frame.pack(fill='both', expand=True)

        self.listbox = tk.Listbox(list_frame, height=6, selectmode='single')
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.listbox.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.listbox.bind('<<ListboxSelect>>', self._on_listbox_select)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="Delete", command=self._delete_selected, width=8).pack(side='left', padx=2)

    def set_books(self, books: List[dict]):
        """Set the list of books."""
        self.books = books
        self._refresh_list()

    def get_books(self) -> List[dict]:
        """Get the current list of books."""
        return self.books

    def set_current_index(self, index: int):
        """Set the currently selected book index."""
        self.current_index = index
        if 0 <= index < len(self.books):
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
            self.listbox.see(index)
        self._refresh_list()

    def get_current_index(self) -> int:
        """Get the currently selected book index."""
        return self.current_index

    def add_book(self, book: dict) -> int:
        """Add a new book and return its index."""
        self.books.append(book)
        self._refresh_list()
        return len(self.books) - 1

    def update_book(self, index: int, book: dict):
        """Update book at index."""
        if 0 <= index < len(self.books):
            self.books[index] = book
            self._refresh_list()

    def _refresh_list(self):
        """Refresh the listbox display."""
        self.listbox.delete(0, tk.END)
        for i, book in enumerate(self.books):
            selection = book.get('selection', '')
            # Truncate long selections
            if len(selection) > 30:
                selection = selection[:27] + "..."
            marker = " *" if i == self.current_index else ""
            self.listbox.insert(tk.END, f"Book {i + 1}: {selection}{marker}")

        # Highlight current
        if 0 <= self.current_index < len(self.books):
            self.listbox.selection_set(self.current_index)

    def _on_listbox_select(self, event):
        """Handle listbox selection."""
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            if index != self.current_index:
                self.current_index = index
                self._refresh_list()
                if self.on_select:
                    self.on_select(index, self.books[index])

    def _new_book(self):
        """Create a new empty book."""
        new_book = {'selection': ''}
        self.books.append(new_book)
        self.current_index = len(self.books) - 1
        self._refresh_list()
        if self.on_select:
            self.on_select(self.current_index, new_book)

    def _delete_selected(self):
        """Delete the currently selected book."""
        if not self.books:
            return

        if len(self.books) == 1:
            # Don't delete last book, just clear it
            self.books[0] = {'selection': ''}
            self._refresh_list()
            if self.on_select:
                self.on_select(0, self.books[0])
            return

        if self.on_delete:
            self.on_delete(self.current_index)

        del self.books[self.current_index]
        if self.current_index >= len(self.books):
            self.current_index = len(self.books) - 1
        self._refresh_list()

        if self.on_select and self.books:
            self.on_select(self.current_index, self.books[self.current_index])


class SelectionBuilder(ttk.Frame):
    """Page selection entry with validation and info display."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self.total_pages = 0

        # Selection entry
        entry_frame = ttk.Frame(self)
        entry_frame.pack(fill='x', pady=5)

        ttk.Label(entry_frame, text="Selection:").pack(side='left')
        self.entry = ttk.Entry(entry_frame, width=50)
        self.entry.pack(side='left', fill='x', expand=True, padx=5)
        self.entry.bind('<KeyRelease>', self._on_entry_change)

        # Info display
        self.info_label = ttk.Label(self, text="Pages: 0 | Needed: 0 | Missing: 0")
        self.info_label.pack(anchor='w')

        # Spread warning display
        self.spread_warning = ttk.Label(self, text="", foreground='#D32F2F')  # Red text
        self.spread_warning.pack(anchor='w')

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=5)

        ttk.Button(btn_frame, text="Add Blank", command=self._add_blank).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Clear", command=self._clear).pack(side='left', padx=2)

    def set_total_pages(self, total: int):
        """Set the total page count for validation."""
        self.total_pages = total

    def get_selection_string(self) -> str:
        """Get the current selection string."""
        return self.entry.get().strip()

    def set_selection_string(self, text: str):
        """Set the selection string."""
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        self._update_info()

    def set_from_pages(self, pages: List[int]):
        """Convert page list to selection string."""
        if not pages:
            self.set_selection_string("")
            return

        # Convert to compact string format
        result = []
        i = 0
        while i < len(pages):
            start = pages[i]
            end = start
            # Find consecutive range
            while i + 1 < len(pages) and pages[i + 1] == pages[i] + 1:
                end = pages[i + 1]
                i += 1

            if start == end:
                result.append(str(start))
            else:
                result.append(f"{start}-{end}")
            i += 1

        self.set_selection_string(",".join(result))

    def get_pages(self) -> List:
        """Parse selection string to list of pages/blanks."""
        text = self.get_selection_string()
        if not text:
            return []

        try:
            return parse_page_selection(text, self.total_pages)
        except Exception:
            return []

    def _on_entry_change(self, event):
        self._update_info()
        if self.on_change:
            self.on_change(self.get_pages())

    def _update_info(self):
        """Update the info label with page counts."""
        pages = self.get_pages()
        count = len(pages)
        needed = ((count + 3) // 4) * 4  # Round up to multiple of 4
        missing = needed - count

        self.info_label.configure(
            text=f"Pages: {count} | Needed for booklet: {needed} | Missing: {missing}"
        )

    def set_spread_warning(self, misaligned: List[Tuple]):
        """Update spread alignment warning.

        Args:
            misaligned: List of (spread_pair, pos1, pos2) for misaligned spreads
        """
        if not misaligned:
            self.spread_warning.configure(text="")
        else:
            warnings = []
            for pair, pos1, pos2 in misaligned:
                warnings.append(f"⚠ Spread {pair[0]}-{pair[1]} misaligned (positions {pos1+1},{pos2+1})")
            self.spread_warning.configure(text=" | ".join(warnings))

    def _add_blank(self):
        """Add a blank marker to selection."""
        current = self.get_selection_string()
        if current:
            self.set_selection_string(current + ",b")
        else:
            self.set_selection_string("b")

    def _clear(self):
        """Clear the selection."""
        self.set_selection_string("")
        if self.on_change:
            self.on_change([])


class BookletMakerGUI(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("Booklet Maker GUI")
        self.geometry("1200x800")

        self.pdf_path = None  # Original file path (PDF or CBZ)
        self.temp_pdf_path = None  # Temp PDF path if CBZ was converted
        self._temp_cropped_pdf = None  # Temp PDF path with crops applied
        self.current_book_index = 0
        self._updating_from_list = False  # Prevent recursive updates

        # Load saved configuration
        self.user_config = load_config()

        # Create UI theme for consistent styling
        self.theme = UITheme()

        self._create_menu()
        self._create_ui()

        # Initialize with one empty book
        self.book_list.set_books([{'selection': ''}])
        self.book_list.set_current_index(0)

        # Save config on window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open...", command=self._open_pdf, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        self.config(menu=menubar)
        self.bind('<Control-o>', lambda e: self._open_pdf())

    def _create_ui(self):
        """Create main UI layout."""
        # Top bar
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', padx=10, pady=5)

        self.file_label = ttk.Label(top_frame, text="No PDF loaded")
        self.file_label.pack(side='left')

        ttk.Button(top_frame, text="Open", command=self._open_pdf).pack(side='left', padx=10)

        # Split double pages button (only if PyMuPDF available)
        if PYMUPDF_AVAILABLE:
            ttk.Button(top_frame, text="Split Double Pages", command=self._split_double_pages).pack(side='left', padx=5)

        self.progress = ttk.Progressbar(top_frame, length=200, mode='determinate')
        self.progress.pack(side='right')

        # Main content - PanedWindow for resizable split
        paned = ttk.PanedWindow(self, orient='horizontal')
        paned.pack(fill='both', expand=True, padx=10, pady=5)

        # Left panel - Thumbnails
        left_frame = ttk.LabelFrame(paned, text="PDF Pages")
        paned.add(left_frame, weight=2)

        self.thumbnail_grid = ThumbnailGrid(left_frame,
                                           on_selection_change=self._on_selection_change,
                                           on_spread_change=self._on_spread_change,
                                           on_hover=self._on_page_hover,
                                           theme=self.theme,
                                           default_crop=self.user_config.get('default_crop', {'top': 0.0, 'bottom': 0.0, 'left': 0.0, 'right': 0.0}))
        self.thumbnail_grid.pack(fill='both', expand=True)

        # Right panel - Preview and options
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        # Page preview
        preview_frame = ttk.LabelFrame(right_frame, text="Page Preview")
        preview_frame.pack(fill='both', expand=True, pady=(0, 10))

        self.page_preview = PagePreview(preview_frame)
        self.page_preview.pack(fill='both', expand=True)

        # Bottom panel - Selection and options
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill='x', padx=10, pady=5)

        # Book list and selection side by side
        books_select_frame = ttk.Frame(bottom_frame)
        books_select_frame.pack(fill='x', pady=5)

        # Book list panel (left)
        book_list_frame = ttk.LabelFrame(books_select_frame, text="Books")
        book_list_frame.pack(side='left', fill='both', padx=(0, 10))

        self.book_list = BookListPanel(book_list_frame,
                                       on_select=self._on_book_select,
                                       on_delete=self._on_book_delete)
        self.book_list.pack(fill='both', expand=True, padx=5, pady=5)

        # Selection builder (right)
        select_frame = ttk.LabelFrame(books_select_frame, text="Page Selection (editing current book)")
        select_frame.pack(side='left', fill='both', expand=True)

        self.selection_builder = SelectionBuilder(select_frame, on_change=self._on_selection_text_change)
        self.selection_builder.pack(fill='x', padx=5, pady=5)

        # Options
        options_frame = ttk.LabelFrame(bottom_frame, text="Output Options")
        options_frame.pack(fill='x', pady=5)

        opts_inner = ttk.Frame(options_frame)
        opts_inner.pack(fill='x', padx=5, pady=5)

        # Reading order
        ttk.Label(opts_inner, text="Reading Order:").grid(row=0, column=0, padx=5)
        self.reading_order = ttk.Combobox(opts_inner, values=['western', 'manga'], width=10, state='readonly')
        self.reading_order.set(self.user_config['reading_order'])
        self.reading_order.grid(row=0, column=1, padx=5)
        self.reading_order.bind('<<ComboboxSelected>>', lambda e: self._update_preview())

        # Signatures
        ttk.Label(opts_inner, text="Signatures:").grid(row=0, column=2, padx=5)
        self.signatures = ttk.Spinbox(opts_inner, from_=1, to=10, width=5)
        self.signatures.set(self.user_config['signatures'])
        self.signatures.grid(row=0, column=3, padx=5)
        self.signatures.bind('<KeyRelease>', lambda e: self._update_preview())

        # Duplex
        ttk.Label(opts_inner, text="Duplex:").grid(row=0, column=4, padx=5)
        self.duplex_mode = ttk.Combobox(opts_inner, values=['auto', 'manual'], width=10, state='readonly')
        self.duplex_mode.set(self.user_config['duplex_mode'])
        self.duplex_mode.grid(row=0, column=5, padx=5)

        # Paper size
        ttk.Label(opts_inner, text="Paper Size:").grid(row=0, column=6, padx=5)
        self.paper_size_labels = {
            'tabloid': 'Tabloid (11x17")',
            'a3': 'A3 (16.5x11.7")',
            'letter': 'Letter (8.5x11")',
            'a4': 'A4 (11.7x8.3")',
            'legal': 'Legal (8.5x14")'
        }
        self.paper_size_keys = {v: k for k, v in self.paper_size_labels.items()}
        paper_display_values = [self.paper_size_labels[k] for k in PAPER_SIZES.keys()]
        self.paper_size = ttk.Combobox(opts_inner, values=paper_display_values, width=16, state='readonly')
        self.paper_size.set(self.paper_size_labels.get(self.user_config['paper_size'], self.paper_size_labels[DEFAULT_PAPER_SIZE]))
        self.paper_size.grid(row=0, column=7, padx=5)

        # Output name
        ttk.Label(opts_inner, text="Output Name:").grid(row=0, column=8, padx=5)
        self.output_name = ttk.Entry(opts_inner, width=25)
        self.output_name.grid(row=0, column=9, padx=5)

        # Generate button and output folder
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill='x', pady=10)

        ttk.Button(btn_frame, text="Generate All Books", command=self._generate).pack(side='right', padx=5)

        # Output folder selection
        self.output_folder_var = tk.StringVar(value=self.user_config['output_folder'])
        ttk.Button(btn_frame, text="Browse...", command=self._browse_output_folder).pack(side='right', padx=5)
        self.output_folder_entry = ttk.Entry(btn_frame, textvariable=self.output_folder_var, width=40)
        self.output_folder_entry.pack(side='right', padx=5)
        ttk.Label(btn_frame, text="Output Folder:").pack(side='right', padx=(0, 5))

    def _cleanup_temp_pdf(self):
        """Clean up temporary PDF file if it exists."""
        if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
            try:
                os.unlink(self.temp_pdf_path)
            except OSError:
                pass  # Ignore cleanup errors
            self.temp_pdf_path = None

    def _open_pdf(self):
        """Open a PDF or CBZ file."""
        path = filedialog.askopenfilename(
            title="Select PDF or CBZ",
            filetypes=[("Comic files", "*.pdf *.cbz"), ("PDF files", "*.pdf"), ("CBZ files", "*.cbz"), ("All files", "*.*")]
        )
        if path:
            # Clean up any previous temp file
            self._cleanup_temp_pdf()

            self.pdf_path = path
            self.file_label.configure(text=f"{Path(path).name}")

            # Set default output name
            self.output_name.delete(0, tk.END)
            self.output_name.insert(0, Path(path).stem + "_book1")

            # Convert CBZ to temp PDF for thumbnail display
            if Path(path).suffix.lower() == '.cbz':
                self.file_label.configure(text=f"{Path(path).name} (converting...)")
                self.update_idletasks()
                try:
                    self.temp_pdf_path = cbz_to_pdf(path)
                    pdf_for_display = self.temp_pdf_path
                    self.file_label.configure(text=f"{Path(path).name}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to convert CBZ:\n{e}")
                    return
            else:
                pdf_for_display = path

            # Load thumbnails
            self.progress['value'] = 0

            def on_progress(current, total):
                self.progress['value'] = (current / total) * 100
                self.update_idletasks()

            self.thumbnail_grid.load_pdf(pdf_for_display, on_progress)
            self.selection_builder.set_total_pages(
                pdfium.PdfDocument(pdf_for_display).__len__()
            )

            # Connect the thumbnail cache to the page preview for hover
            if self.thumbnail_grid.cache:
                self.page_preview.set_cache(self.thumbnail_grid.cache)

            # Set default output folder only if not already set from config
            if not self.output_folder_var.get():
                self.output_folder_var.set(str(Path(path).parent / "prints"))

    def _split_double_pages(self):
        """Split double-page spreads in the currently loaded file."""
        if not self.pdf_path:
            messagebox.showerror("Error", "No file loaded")
            return

        # Get the PDF to process (use temp PDF if we converted from CBZ)
        pdf_to_split = self.temp_pdf_path if self.temp_pdf_path else self.pdf_path

        self.file_label.configure(text=f"{Path(self.pdf_path).name} (splitting...)")
        self.update_idletasks()

        try:
            # Split the double pages
            result = split_double_pages(pdf_to_split)

            if result['splits_made'] == 0:
                self.file_label.configure(text=f"{Path(self.pdf_path).name}")
                messagebox.showinfo("No Changes", "No double-page spreads detected.")
                return

            # Clean up old temp file if it's different from the new one
            old_temp = self.temp_pdf_path
            self.temp_pdf_path = result['output_path']

            if old_temp and old_temp != result['output_path'] and os.path.exists(old_temp):
                try:
                    os.unlink(old_temp)
                except OSError:
                    pass

            # Reload thumbnails from the split PDF
            self.progress['value'] = 0

            def on_progress(current, total):
                self.progress['value'] = (current / total) * 100
                self.update_idletasks()

            self.thumbnail_grid.load_pdf(self.temp_pdf_path, on_progress)
            self.selection_builder.set_total_pages(
                pdfium.PdfDocument(self.temp_pdf_path).__len__()
            )

            # Update page preview with new cache
            if self.thumbnail_grid.cache:
                self.page_preview.set_cache(self.thumbnail_grid.cache)

            # Clear any existing selection since page numbers changed
            self.thumbnail_grid.clear_selection()
            self.selection_builder.set_selection_string("")

            # Auto-mark split pairs as spreads
            if result.get('split_pairs'):
                self.thumbnail_grid.spread_pairs = result['split_pairs'].copy()
                # Highlighting is applied during thumbnail creation in _add_thumbnail()
                # Just trigger alignment validation
                self._on_spread_change(result['split_pairs'])

            self.file_label.configure(text=f"{Path(self.pdf_path).name}")
            messagebox.showinfo(
                "Split Complete",
                f"Split {result['splits_made']} double-page spread(s).\n"
                f"Pages: {result['original_pages']} → {result['output_pages']}\n"
                f"Automatically marked {len(result.get('split_pairs', []))} spread pair(s)."
            )

        except Exception as e:
            self.file_label.configure(text=f"{Path(self.pdf_path).name}")
            messagebox.showerror("Error", f"Failed to split pages:\n{e}")

    def _browse_output_folder(self):
        """Open folder selection dialog for output directory."""
        initial_dir = self.output_folder_var.get() or (Path(self.pdf_path).parent if self.pdf_path else None)
        folder = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=initial_dir
        )
        if folder:
            self.output_folder_var.set(folder)

    def _save_config(self):
        """Save current settings to config file."""
        paper_size_key = self.paper_size_keys.get(self.paper_size.get(), DEFAULT_PAPER_SIZE)
        config = {
            "reading_order": self.reading_order.get(),
            "signatures": int(self.signatures.get()),
            "duplex_mode": self.duplex_mode.get(),
            "paper_size": paper_size_key,
            "output_folder": self.output_folder_var.get(),
            "default_crop": self.thumbnail_grid.default_crop
        }
        save_config(config)

    def _on_close(self):
        """Handle window close - save config, cleanup, and exit."""
        self._save_config()
        self._cleanup_temp_pdf()
        self.destroy()

    def _on_selection_change(self, pages: List[int]):
        """Handle selection change from thumbnail grid."""
        self.selection_builder.set_from_pages(pages)
        self._save_current_book()
        self._update_preview()
        self._check_spread_alignment()

    def _on_selection_text_change(self, pages: List):
        """Handle selection change from text entry."""
        self.thumbnail_grid.set_selection([p for p in pages if p != "blank"])
        self._save_current_book()
        self._update_preview()
        self._check_spread_alignment()

    def _check_spread_alignment(self):
        """Check and display spread alignment warnings."""
        pages = self.selection_builder.get_pages()
        misaligned = self.thumbnail_grid.check_spread_alignment(pages)
        self.selection_builder.set_spread_warning(misaligned)

    def _on_spread_change(self, spread_pairs: List):
        """Handle spread pairs change from thumbnail grid."""
        self._check_spread_alignment()

    def _on_book_select(self, index: int, book: dict):
        """Handle book selection from list."""
        self._updating_from_list = True
        self.current_book_index = index

        # Load the book's selection into the editor
        selection = book.get('selection', '')
        self.selection_builder.set_selection_string(selection)

        # Update thumbnail selection
        pages = self.selection_builder.get_pages()
        self.thumbnail_grid.set_selection([p for p in pages if p != "blank"])

        self._update_preview()
        self._updating_from_list = False

    def _on_book_delete(self, index: int):
        """Handle book deletion."""
        pass  # BookListPanel handles the deletion itself

    def _save_current_book(self):
        """Save current selection to the current book."""
        if self._updating_from_list:
            return

        selection = self.selection_builder.get_selection_string()
        books = self.book_list.get_books()

        if 0 <= self.current_book_index < len(books):
            books[self.current_book_index]['selection'] = selection
            self.book_list.update_book(self.current_book_index, books[self.current_book_index])

    def _on_page_hover(self, page_num: int):
        """Handle hover over a page thumbnail."""
        crops = self.thumbnail_grid.page_crops.get(page_num)
        self.page_preview.show_page(page_num, crops)

    def _update_preview(self):
        """Legacy method - no longer used since we replaced booklet layout with page preview."""
        pass

    def _generate(self):
        """Generate all booklets."""
        if not self.pdf_path:
            messagebox.showerror("Error", "No PDF loaded")
            return

        # Save current selection first
        self._save_current_book()

        # Get all books with non-empty selections
        books = self.book_list.get_books()
        all_selections = [b['selection'] for b in books if b.get('selection', '').strip()]

        if not all_selections:
            messagebox.showerror("Error", "No pages selected in any book")
            return

        # Get options
        output_name = self.output_name.get() or Path(self.pdf_path).stem
        # Remove _bookN suffix for folder name
        if '_book' in output_name:
            output_name = output_name.rsplit('_book', 1)[0]

        try:
            # Determine input PDF (use temp_pdf_path if CBZ was converted)
            input_pdf = self.temp_pdf_path if self.temp_pdf_path else self.pdf_path

            # Get crop data from thumbnail grid
            page_crops_dict = self.thumbnail_grid.get_page_crops()

            # Apply crops if any exist
            if page_crops_dict:
                try:
                    from src.services.crop_service import CropService
                    from src.models import PageCropData

                    # Convert dict to list of PageCropData
                    crops = [
                        PageCropData.from_dict(pnum, crop_data)
                        for pnum, crop_data in page_crops_dict.items()
                    ]

                    crop_service = CropService()
                    cropped_pdf_path = crop_service.apply_crops_to_pdf(
                        pdf_path=Path(input_pdf),
                        crops=crops
                    )

                    # Track for cleanup
                    self._temp_cropped_pdf = str(cropped_pdf_path)
                    input_for_booklet = str(cropped_pdf_path)

                except Exception as e:
                    messagebox.showerror("Error", f"Failed to apply crops:\n{e}")
                    return
            else:
                input_for_booklet = input_pdf

            # Convert display label back to paper size key
            paper_size_key = self.paper_size_keys.get(self.paper_size.get(), DEFAULT_PAPER_SIZE)

            output_files = generate_booklet(
                input_path=input_for_booklet,
                page_selections=all_selections,
                reading_order=self.reading_order.get(),
                num_signatures=int(self.signatures.get()),
                duplex_mode=self.duplex_mode.get(),
                output_name=output_name,
                paper_size=paper_size_key,
                output_dir=self.output_folder_var.get() or None
            )

            messagebox.showinfo("Success",
                               f"Generated {len(output_files)} files:\n" +
                               "\n".join(Path(f).name for f in output_files))

            # Save settings after successful generation
            self._save_config()

        except Exception as e:
            messagebox.showerror("Error", f"Generation failed:\n{e}")

        finally:
            # Cleanup temp cropped PDF
            if self._temp_cropped_pdf and os.path.exists(self._temp_cropped_pdf):
                try:
                    os.unlink(self._temp_cropped_pdf)
                    self._temp_cropped_pdf = None
                except:
                    pass  # Best effort cleanup


def main():
    app = BookletMakerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
