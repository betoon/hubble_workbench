# Hubble Workbench 2.1.0

Prepared October 20, 2026. Local source release; no installer/executable has been built or published in this pass.

## New in this release

- Explorer Image layers dialog: visibility, individual opacity, and bottom-to-top ordering. Settings persist in projects alongside the global overlay controls.
- Portable project export: a new folder containing project.json, deduplicated referenced FITS images, a SHA-256 manifest and a results folder. Relative paths allow moving the folder; opening verifies its image files before applying the project.
- Optional resolution matching for RGB/LRGB: user-supplied FWHM estimates, circular Gaussian smoothing to the broadest assigned channel, preserved missing-pixel masks, and recorded alignment/FITS provenance.
- Updated beginner manual, Wizard guide and roadmap. The build script uses the existing spec and a versioned output directory, refuses to overwrite an existing release, and no longer deletes prior build/output folders or upgrades packages automatically.

## Validation

- 131 automated tests passed on Windows/Python 3.12, including Gaussian-width checks, mask/edge handling, portable deduplication and relocation, checksum rejection, traversal rejection, cancellation, layer opacity/order, and the existing astronomy workflows.
- End-to-end offline check: generate four WCS FITS channels, align and resolution-match them, export and relocate the bundle, reopen it, and compose LRGB without network access.
- Desktop inspection verified the new dialogs and layer reordering using a cached real Chandra image and a synthetic comparison image. The Wizard action layout was adjusted to keep its overlay button visible.
- Earlier archive validation exercised the replacement Chandra API and one public FITS download. No fresh remote archive validation was required for these local features.

## Installation / use

Extract the source archive into a new writable folder. Install Python and dependencies from requirements.txt, then run launch_hubble_workbench.bat. The archive includes tests and user documentation. It intentionally excludes settings, credentials, image downloads, logs and user outputs.

To create a Windows executable, install PyInstaller and requirements.txt in your build environment, then run build.bat. Output is dist/2.1.0/Hubble_Workbench/. Executable packaging still requires a separate build and runtime smoke test before distributing that executable.

## Limits

Resolution matching is a visual approximation based on supplied values and local WCS scales. It does not measure spatially varying telescope PSFs, include the extra blur introduced by resampling, or calibrate different instruments. Use approximately orthogonal, small-field grids; kernels above 64 pixels sigma are rejected. Existing FITS files remain untouched.

Portable folders include all referenced local FITS records, even downloaded images not assigned to RGB. Missing referenced files prevent export. Move the entire folder and keep its manifest/data together. Existing preview PNG/TIFF exports are not packaged; they can be regenerated. Checksums detect accidental asset changes, not authenticity of a third-party project.

Explorer overlays remain independently stretched previews, limited to eight local images. Source-colored overlays are for comparison rather than calibrated flux measurements.

Gaussian kernel implementation uses Astropy convolution: https://docs.astropy.org/en/stable/convolution/index.html
