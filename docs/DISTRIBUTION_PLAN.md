# Application Distribution Plan for BookletMaker

## Goal
Prepare the application for distribution so users on Windows, macOS, and Linux can download and run it without needing Python installed.

---

## Overview

**Current State:**
- Python Tkinter GUI application
- Entry points: `booklet_gui.py` (GUI), `booklet_maker.py` (CLI)
- Dependencies with C extensions: pypdfium2, Pillow, PyMuPDF
- No existing packaging configuration

**Distribution Strategy:**
- Use PyInstaller to create standalone executables
- GitHub Actions for automated cross-platform builds
- GitHub Releases for distribution

---

## Implementation Plan

### Phase 1: Fix Config File Location

The current config path uses `Path(__file__).parent` which breaks in bundled apps.

**Files to modify:**
- `booklet_gui.py` (lines 59-61)
- `src/services/config_service.py` (lines 31-33)

**Changes:**
```python
def get_app_data_dir() -> Path:
    """Get platform-appropriate application data directory."""
    app_name = "BookletMaker"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / app_name
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        return Path(xdg_config) / app_name

def is_frozen() -> bool:
    """Check if running as PyInstaller bundle."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
```

### Phase 2: Create Package Metadata

**Create `pyproject.toml`:**
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bookletMaker"
version = "1.0.0"
description = "Convert PDFs and CBZ files into print-ready booklet format"
requires-python = ">=3.10"
dependencies = [
    "pypdf>=4.0.0",
    "reportlab>=4.0.0",
    "pypdfium2>=4.0.0",
    "Pillow>=9.0.0",
    "PyMuPDF>=1.23.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0.0", "pytest-cov>=4.0.0", "pyinstaller>=6.0.0"]

[project.gui-scripts]
booklet-maker-gui = "booklet_gui:main"
```

### Phase 3: Create Placeholder Application Icons

**Create `assets/` directory with placeholder icons:**
- `icon.ico` - Windows (multi-resolution: 256, 128, 64, 48, 32, 16)
- `icon.icns` - macOS (512x512@2x, 512x512, 256x256, etc.)
- `icon.png` - Linux (512x512)

Note: Will generate simple "BM" text-based icons as placeholders. Can be replaced later with custom artwork.

### Phase 4: Create PyInstaller Spec File

**Create `bookletMaker.spec`:**
- Configure hidden imports for C extension dependencies
- Platform-specific settings (windowed mode, icons)
- Bundle src/ package and assets

Key hidden imports needed:
- pypdfium2, pypdfium2._helpers
- PIL, PIL._imaging
- reportlab, reportlab.graphics
- fitz (PyMuPDF)
- pypdf

### Phase 5: GitHub Actions CI/CD

**Create `.github/workflows/build-release.yml`:**

```yaml
on:
  push:
    tags: ['v*']

jobs:
  build-windows:
    runs-on: windows-latest
    # Build .exe, create .zip

  build-macos:
    runs-on: macos-latest
    # Build .app bundle, create .dmg

  build-linux:
    runs-on: ubuntu-22.04
    # Build executable, create .tar.gz

  create-release:
    needs: [build-windows, build-macos, build-linux]
    # Upload all artifacts to GitHub Release
```

### Phase 6: Documentation

**Update README.md with:**
- Download links for each platform
- Installation instructions
- Platform-specific notes (SmartScreen warnings, macOS Gatekeeper)

---

## Platform Considerations

### Windows
- Unsigned executables trigger SmartScreen warnings
- Users click "More info" → "Run anyway"
- (Signing skipped - open source project, users can build from source)

### macOS
- Unsigned apps show "unidentified developer" warning
- Users right-click → Open to bypass
- (Signing skipped for now - can add later if needed)

### Linux
- tar.gz extraction works across most distros
- Include .desktop file for menu integration

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `pyproject.toml` | Create |
| `bookletMaker.spec` | Create |
| `.github/workflows/build-release.yml` | Create |
| `assets/icon.ico`, `icon.icns`, `icon.png` | Create |
| `booklet_gui.py` | Modify config path |
| `src/services/config_service.py` | Modify config path |
| `README.md` | Add installation instructions |
| `.gitignore` | Add build artifacts |

---

## Verification

1. **Local build test:** Run `pyinstaller bookletMaker.spec` on dev machine
2. **Cross-platform test:** Trigger GitHub Actions, download artifacts
3. **Smoke test:** Open app, load PDF, generate booklet on each platform
4. **Config persistence:** Verify settings save/load correctly in packaged app

---

## Release Process

1. Update version in `pyproject.toml`
2. Create git tag: `git tag v1.0.0`
3. Push tag: `git push origin v1.0.0`
4. GitHub Actions automatically builds and creates release
5. Edit release notes if needed
