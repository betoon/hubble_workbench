# Hubble Workbench Modularization Plan

Branch: `v2.0.1-development`

This plan is based on the working app copy at:

`C:\Users\brian\Documents\Codex\my_programs\Astronomy\Hubble_Workbench\hubble_workbench.py`

The GitHub checkout at `C:\Users\brian\Documents\GitHub\hubble_workbench` is connected to `https://github.com/betoon/hubble_workbench.git`, but it does not yet contain the application source files. This document intentionally does not modify the existing app code.

## Current Shape

`hubble_workbench.py` is about 3,487 lines.

The top of the file contains imports, app constants, settings helpers, target galleries, filter/catalog constants, FITS helpers, and image-processing helpers.

The main app class starts at `class HubbleWorkbench(tk.Tk)` around line 603 and contains most of the behavior: Tkinter setup, tab construction, dependency checks, MAST/HLA searches, product scoring, RGB candidate selection, downloads, FITS preview/conversion, RGB composition, tuning, presets, project save/load, and export.

## Target Layout

Use a package while keeping `hubble_workbench.py` as the public launcher until the refactor is proven stable.

```text
hubble_workbench.py
hubble_workbench_app/
  __init__.py
  app.py
  paths.py
  settings.py
  catalogs.py
  dependencies.py
  fits_io.py
  image_processing.py
  mast_search.py
  product_scoring.py
  downloads.py
  project_files.py
  ui/
    __init__.py
    setup_tab.py
    browser_tab.py
    convert_tab.py
    compose_tab.py
    widgets.py
```

## Module Responsibilities

`hubble_workbench.py`

- Thin compatibility launcher.
- Imports `HubbleWorkbench` from `hubble_workbench_app.app`.
- Keeps `python hubble_workbench.py`, the batch launcher, and the PyInstaller spec working.

`hubble_workbench_app/paths.py`

- `APP_DIR`, `DOWNLOAD_DIR`, `OUTPUT_DIR`, `NOTES_DIR`, `SETTINGS_PATH`, `MESSIER_LIST_PATH`.
- Preview-size constants.

`hubble_workbench_app/settings.py`

- `load_settings`, `save_settings`, and `SETTINGS`.

`hubble_workbench_app/catalogs.py`

- `messier_radius`, `load_messier_gallery_items`.
- `TARGET_GALLERY`, `JWST_TARGET_GALLERY`, `TELESCOPE_CHOICES`, `SOLAR_SYSTEM_TARGETS`, `TARGET_ALIASES`.
- JWST/HST filter constants, `RGB_FILTER_TOKENS`, and `TARGET_RECIPES`.

`hubble_workbench_app/dependencies.py`

- `optional_imports`.
- Late-bound optional dependency names such as `FITS`, `OBSERVATIONS`, and `TIF_FILE` if they are currently assigned globally.

`hubble_workbench_app/fits_io.py`

- `first_image_hdu`.
- `find_fits_liberator_cli`.
- `fits_liberator_stretch_args`.
- `read_liberated_channel`.
- `run_fits_liberator_channel`.

`hubble_workbench_app/image_processing.py`

- `normalize_image`, `normalize_float_channel`.
- `resize_to_match`, `resize_float_to_match`.
- Preview downsampling helpers.
- `float_rgb_to_uint8`, `float_rgb_to_uint16`.
- Border/gap/presentation cleanup helpers.

`hubble_workbench_app/mast_search.py`

- Target parsing and search helpers.
- MAST/HLA query flow can move here as a mixin while preserving method names.

`hubble_workbench_app/product_scoring.py`

- Product identity, filtering, labels, scoring, RGB grouping, and candidate selection.

`hubble_workbench_app/downloads.py`

- Download orchestration, HLA download handling, MAST individual downloads, manifest extraction, and RGB path matching.

`hubble_workbench_app/project_files.py`

- Output prefixing, project state, project save/open, latest output opening, composite exports, and notes/output filename handling.

`hubble_workbench_app/ui/`

- Move UI construction last because it depends heavily on `self.*` state and callback names.
- Start with mixins so callbacks keep their existing names.
- Candidate split: setup tab, browser tab, convert tab, compose tab, and shared widgets.

## Migration Sequence

1. Copy the current application source into the GitHub checkout.
2. Commit that baseline unchanged on `v2.0.1-development`.
3. Keep `hubble_workbench.py` as the launcher.
4. Extract pure modules first: `paths.py`, `settings.py`, `catalogs.py`, `image_processing.py`, and `fits_io.py`.
5. After each extraction, run smoke tests and a compile check.
6. Extract method groups as mixins while leaving method names unchanged.
7. Move UI construction last.
8. Only after behavior is stable, consider renaming files or changing the PyInstaller entry point.

## Preservation Rules

- Do not change button callback names during the first pass.
- Do not rename `self.*` attributes during the first pass.
- Do not change launch behavior: `python hubble_workbench.py` must still start the app.
- Do not change output folders or settings filenames.
- Do not change `Hubble_Workbench.spec` until the package import path is proven.
- Prefer mechanical moves over rewrites.
- Validate after every small extraction.

## Suggested Verification

Run after each extraction:

```text
python -m py_compile hubble_workbench.py
python -m unittest tests.test_generated_smoke
```

Then manually verify that the app opens, dependency status loads, MAST searches run, product lists refresh, FITS preview works, RGB composition renders, project save/load works, and PNG/TIFF exports write to `outputs/`.

## Files To Keep Out Of Source Control By Default

The working app folder contains generated/runtime artifacts such as `build/`, `dist/`, `downloads/`, `logs/`, `outputs/`, `test_logs/`, and `__pycache__/`. Those should not be brought into the GitHub repo as source unless there is a specific reason.
