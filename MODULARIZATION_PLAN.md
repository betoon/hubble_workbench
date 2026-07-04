# Hubble Workbench Modularization Plan

Branch: `v2.0.1-development`

This branch now contains the working Space Telescope Workbench application from the original local app folder, with the large main script split into focused helper modules.

Main launcher/app file:

`hubble_workbench_v2_observatory_explorer.py`

Package folder:

`hubble_workbench_app/`

## Current Shape

The main file is now mostly the Tkinter app shell and UI construction. It keeps:

- app startup and `HubbleWorkbench` class setup
- tab/layout builders
- direct callback wrapper methods used by Tkinter buttons and smoke tests
- final app startup helpers such as `run_app`

Most non-UI behavior has moved into mixin modules under `hubble_workbench_app/`.

## Current Module Map

`paths.py`

- App folders, runtime output folders, log folders, settings path, preview-size constants, and product token constants.

`settings.py`

- Shared `SETTINGS`, `load_settings`, and `save_settings`.

`catalogs.py`

- Target galleries, telescope choices, Messier loading, filter constants, RGB filter tokens, and target recipes.

`fits_io.py`

- Optional astronomy imports, FITS reading, FITS Liberator detection and channel loading.

`image_processing.py`

- Image normalization, preview downsampling, RGB conversion, resizing, gap fill, and crop helpers.

`app_logging.py`

- Debug log setup, timing log, global exception logging, path diagnostics, and debug method wrapping.

`developer_tools.py`

- Developer Tools menu, developer setting saves, diagnostic JSON writing, and current target names for logs.

`dependency_status.py`

- Dependency status panel and checks for missing `astroquery` / `astropy`.

`browser_activity.py`

- Busy state, Stop button behavior, progress text, timeout handling, and download progress UI.

`target_gallery.py`

- Hubble/JWST gallery selection, target recipe lookup, target loading, HLA gallery search helper, and output prefix helper.

`quality_settings.py`

- High-quality options, stretch setting saves, auto-compose trigger, and advanced stretch reset.

`mast_helpers.py`

- Target variants, radius parsing, MAST observation query helpers, product classification helpers, labels, and RGB group helpers.

`product_scoring.py`

- Product identity, product quality scoring, RGB set scoring, extra download row selection, and Easy RGB explanation text.

`search_workflow.py`

- Search MAST, Easy RGB Image, Easy High Quality, table value conversion, and normal MAST search completion.

`hla_workflow.py`

- Hubble Legacy Archive fallback search, HLA product fetching/parsing, HLA filename/sort helpers, and HLA search completion.

`product_browser.py`

- Product filtering/list refresh, RGB candidates and suggested sets, copy/select actions, Get Products, Get All Products, product row normalization/sorting, and product-load completion.

`better_sources.py`

- Find Better Sources, better-source scoring, better-source completion, Completeness Check, completeness reports, and completion handling.

`download_workflow.py`

- Selected product downloads, HLA product downloads, manifest extraction, RGB path matching, and download completion.

`preview_workflow.py`

- FITS preview/convert workflow, preview output saves, channel selection, and loading latest RGB sets.

`compose_workflow.py`

- RGB composition, image tuning, presets, preview updates, Easy RGB completion, and output preparation.

`project_workflow.py`

- Composite export, latest output opening, project save, and project open.

`app_utilities.py`

- Canvas image display, opening folders/files, and close/save behavior.

## What Remains In The Main File

The main file intentionally still owns UI construction:

- `setup_style`
- `build_ui`
- `build_setup_tab`
- `build_browser_tab`
- `build_rgb_candidate_column`
- `build_observatory_tab`
- `build_convert_tab`
- `build_compose_tab`
- `build_tuning_slider`

This is deliberate. The UI builders are the clearest wiring diagram for the app and heavily reference `self.*` state and callback names. Moving them should be optional and lower priority than preserving a stable working app.

The main file also keeps small wrapper methods for button callbacks. These wrappers preserve existing method names and keep the generated smoke test happy while the real implementations live in mixins.

## Preservation Rules

- Keep button callback method names unchanged.
- Keep `self.*` attribute names unchanged.
- Keep launch behavior unchanged: `launch_hubble_workbench.bat` and the PyInstaller spec still point at `hubble_workbench_v2_observatory_explorer.py`.
- Keep output folders and settings filenames unchanged.
- Prefer mechanical moves over rewrites.
- Validate after every extraction.

## Verification

Run after each extraction:

```text
python -m py_compile hubble_workbench_v2_observatory_explorer.py hubble_workbench_app\*.py
python -m unittest tests.test_generated_smoke
```

On Windows PowerShell, expand the module list if the wildcard is not accepted by `py_compile`:

```text
$files = @('hubble_workbench_v2_observatory_explorer.py') + (Get-ChildItem .\hubble_workbench_app -Filter *.py | ForEach-Object { $_.FullName })
python -m py_compile @files
python -m unittest tests.test_generated_smoke
```

Manual verification should still include opening the app, checking dependency status, running a target search, loading products, previewing a FITS file, composing RGB, saving/loading a project, and exporting PNG/TIFF outputs.

## Files To Keep Out Of Source Control By Default

Generated/runtime artifacts such as `build/`, `dist/`, `downloads/`, `logs/`, `outputs/`, `test_logs/`, and `__pycache__/` should stay out of source control unless there is a specific reason.