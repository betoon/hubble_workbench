# Hubble Workbench Roadmap

Updated October 20, 2026.

## Current status

The earlier roadmap's major image-workflow items are now implemented: Observatory Explorer, multi-archive image projects, guided RGB selection, LRGB composition, public Chandra observation-image search, and Explorer image overlays. The available workflows and limits are documented in `IMAGE_WIZARD_GUIDE.md`.

## Available features

### Observatory Explorer

- Hubble/JWST observation summaries, source/instrument filters, RGB readiness and product guidance.
- Sky markers, metadata footprints, coverage reports, CSV/report exports and observation selection.
- Wizard source status, targets, bands, available/missing files and RGB/L assignments in project reports.
- Per-source and combined Wizard coverage layers; requested fields remain distinct from archive/FITS boundaries.
- Click a Wizard footprint to open its matching image record.
- Display up to eight downloaded FITS images as WCS-registered grayscale or source-colored overlays with adjustable opacity.
- Save/restore the selected layer, overlay records, mode and opacity. Local overlays reopen offline; old projects clear previous Wizard state.

### Image Wizard and composition

- Pan-STARRS, DSS, WISE, Spitzer, GALEX, curated Chandra and loaded HST/JWST products.
- Chandra Archive: name/coordinate searches of public observation FITS images through the replacement CDA API, with observation identifiers and full/central-field labels.
- Verified reusable downloads, cancellation, previews, coverage inspection and shared-sky alignment.
- Suggest RGB prefers mosaic/combined products and uses local availability as a tie-breaker while keeping targets, instruments and sources separate.
- Optional L channel and strength for guided LRGB, with four-image WCS checks and no luminance fill across missing RGB data.
- Saved assignments, aligned FITS files, provenance, tuning and PNG/TIFF exports through Color Composer.

## Validation completed

- Full local unittest discovery: 131 tests passed, including Chandra parsing/search, local overlays, restoration and earlier RGB/LRGB workflows.
- Live replacement Chandra API query around Centaurus A returned 50 image records; downloaded and validated one public ACIS-I FITS image and its WCS.
- Desktop checks in an isolated copy verified Wizard source controls, loading local overlays, and switching between source colors and grayscale.
- Earlier desktop checks verified coverage labels/click-through and L assignment. Automated tests cover RGB/LRGB, missing files, WCS alignment, RA wrap, project restoration and stale asynchronous results.
- Network behavior depends on the remote archives. The live Chandra check is one representative query/download, not an exhaustive archive survey.

## Scope and limits

- Chandra Archive searches public image products; it does not access proprietary observations or extract new energy bands from event lists. The curated Chandra option remains available.
- Image overlays are independently stretched display previews, not calibrated flux comparisons. Original images and exported science files are not modified by overlay display.
- Overlay preview is limited to eight selected local images, with bounded sampling/raster sizes. Missing pixels remain transparent.
- Different resolutions, epochs and instrument responses still need user judgment.

## Completed in 2.1.0

- Per-image visibility, opacity and ordering, persisted with projects.
- Portable project folders with deduplicated FITS files, relative paths and SHA-256 verification.
- Optional user-estimated Gaussian resolution matching with RGB/L support and provenance.
- Updated beginner documentation and versioned source release/build preparation.

## Possible future work

No remaining feature from the earlier major-feature shortlist is currently marked blocked or required for ordinary use. Further work should follow practical feedback. Potential larger additions include Chandra event-list processing and measured, spatially varying PSF matching; these are new optional scope, not promised work in this pass.

## Maintenance

Preserve callback names, launch paths, output conventions and older project compatibility. See `MODULARIZATION_PLAN.md` for the module layout. Run relevant tests after changes and keep this roadmap synchronized with shipped behavior.
