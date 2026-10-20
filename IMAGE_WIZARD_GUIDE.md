# Image Wizard

Open **Image Wizard** to find, inspect and combine public astronomy images.

1. Choose a source and target. Names such as M51 work for most archives; decimal RA, Dec also works. The Chandra option uses curated names such as Orion, Cas A or Crab; Chandra Archive accepts ordinary target names or coordinates.
2. Choose **Find images**. Select rows to review estimated download sizes and coverage. This step prepares cutouts but does not download science files.
3. **Preview selected** downloads one band and displays it. **Suggest RGB** chooses three distinct available bands from one source/instrument. Review the choices, or assign selected rows with **Use as R/G/B**.
4. **Build RGB** downloads the assigned images, aligns celestial coordinates, checks common valid pixels, and opens the Color Composer. Shared-coverage cropping is on by default. Areas without measurements remain missing; no sky features are invented.
5. Tune the image and use the existing output controls to save PNG, TIFF and notes. Project JSON includes source URLs, local files, color assignments and alignment settings. Each wizard build also saves aligned FITS files, a preview and project JSON in an `outputs/archive_project_*` folder.

## Available sources

| Source | Available data | Limits |
| --- | --- | --- |
| Pan-STARRS | Optical g/r/i/z/y FITS cutouts | North of declination -30 degrees; 0.25 arcsecond pixels, maximum 6000 pixels per side. Cutout pixel control does not resample PS1. |
| DSS | Blue, red and infrared photographic survey cutouts | Historical reference imagery; varying resolution and sky coverage. |
| WISE | Four infrared bands through SkyView | Broad survey resolution; display colors are false color. |
| Spitzer | IRAC mosaics, with calibrated exposures as fallback | Up to 200 mosaic rows or 20 exposure rows per band; files can extend beyond the requested field. Different epochs may be returned. |
| GALEX | Near-UV and far-UV cutouts | Two bands: no automatic three-band RGB. Preview them or manually combine with another overlapping source. |
| Chandra | Curated OpenFITS images and energy bands | Curated target names; some targets have only one broad band. |
| Chandra Archive | Public observation FITS images from the CDA image service | Name or coordinate search; full and central fields may both appear. Often a single broad energy band; this is not event-list reprocessing or proprietary-data access. |
| Loaded Hubble/JWST | Current MAST Browser FITS products | Run the existing MAST search and load products first, then import them here. |

## Downloads and coverage

The wizard streams downloads and reports file progress. Verified cached files are reused. **Stop** interrupts at the next network/chunk or processing checkpoint; a pending request must finish or time out first. Partial files resume when the server provides a validator and supports byte ranges, otherwise restart safely. These controls apply to the Image Wizard; existing MAST buttons retain their own workflow.

Dashed coverage outlines show the requested cutout field, not a measured detector footprint. Solid archive polygons or downloaded FITS outlines show available boundaries. Actual common valid-pixel coverage is measured during alignment. Footprints can contain empty areas and do not guarantee useful signal. Very large alignment grids are reduced to four million pixels to limit memory use. Cropping removes exterior bounds; internal gaps remain missing.

Automatic colors map longer wavelengths to red and shorter wavelengths to blue. Cross-source assignments are manual and produce display composites, not calibrated photometry. Different resolutions, epochs and instrumental artifacts still require judgment. A project can be reopened offline while its downloaded and aligned files remain in their saved locations. SkyView download URLs are temporary; repeat Find images if an uncached old URL has expired.

Archive references: [Pan-STARRS](https://spacetelescope.github.io/mast_notebooks/notebooks/PanSTARRS/PS1_image/PS1_image.html), [SkyView](https://skyview.gsfc.nasa.gov/), [IRSA SIA](https://irsa.ipac.caltech.edu/ibe/sia.html), [Chandra OpenFITS](https://www.chandra.harvard.edu/photo/openFITS/xray_data.html). Preserve archive acknowledgments when sharing images.

## Explorer coverage layers

In Observatory Explorer, choose **Image Wizard: All** or an individual archive in the **Layer** selector. These views use records already loaded in Image Wizard, without another search or download. MAST sensor, best-candidate, and overlap filters do not apply to Wizard layers. Dashed outlines are requested fields; solid outlines are archive or FITS boundaries. Unknown coverage is not drawn, and boundaries alone do not guarantee useful shared pixels.

Click inside a footprint to select its record and open Image Wizard. Use Preview selected or assign channels there. Saving a project preserves the selected Explorer layer along with the existing Wizard records and assignments. Older projects default to the normal MAST layer and clear any previous Wizard records. Missing saved files are reported when loading; re-download them in Image Wizard before composition.

## How Suggest RGB chooses images

Automatic suggestions stay within one source, instrument, and target and require three distinct image records/bands. Mosaic, drizzled, and combined products rank ahead of calibrated exposures; already-downloaded files break ties between equal-quality products. Wavelength-based choices retain a short, middle, and long wavelength band. Named channel assignments, such as Chandra energy bands, are preserved when selected.

The status message explains the suggested set. Product metadata and local availability do not prove matching resolution, epoch, or useful sky overlap: review the footprints and let Build RGB verify common coverage. Manual cross-source assignments remain available.

## Guided LRGB: optional luminance/detail image

1. Assign or suggest the usual red, green and blue images.
2. Select one image with useful detail over the same sky region and choose **Use as L**. The L image may be from another source, but differing resolution, epoch and instrumental response still need judgment.
3. Set **Luminance strength** from 0 to 1 (default 0.5). Zero leaves the color intensities unchanged; larger values apply more of the independently stretched L brightness.
4. Choose **Build RGB / LRGB**. All four images must have valid celestial WCS and common valid pixels. Shared-coverage cropping considers all four images. Outside shared valid pixels, luminance is not applied.
5. Tune and export in Color Composer as usual. Save the project to preserve assignments, strength, aligned files and provenance. Rebuild after changing strength or assignments. **Clear L**, then rebuild, produces ordinary RGB.

This is a display enhancement. RGB channels receive the same per-pixel gain to preserve color ratios; gain is limited to avoid clipping individual channels. Completely black RGB pixels stay black. LRGB does not add missing measurements, match point-spread functions, or produce calibrated photometry. Missing or invalid L files stop LRGB composition; it does not silently fall back to image-size alignment. L is applied only while the Composer uses the RGB paths from that Wizard build.


## Chandra Archive searches

Choose **Chandra Archive**, enter a target name or decimal RA, Dec, and choose **Find images**. Field width is sent as the image-search size in degrees; results are whole archive images, not resized cutouts, so the pixel control does not resample them. Rows show energy range, observation ID, and full/central-field variant. Search retrieves metadata only. Preview or Download selected retrieves the FITS file through the existing verified cache.

Different observations of the same broad energy band do not create three distinct RGB bands. Preview them, compare them as overlays, use one as an intentional manual channel, or retain the curated Chandra option for published energy-band sets. Actual footprints are read from downloaded FITS WCS; the search does not fabricate detector boundaries.

The adapter uses the [replacement CDA image API](https://cxcfps.cfa.harvard.edu/cda/footprint/cdaview.html). The service covers public observation images and may not provide an image for every observation. Full dataset/event-file analysis remains a separate Chandra processing workflow.

## Explorer image overlays

1. Download the desired images in Image Wizard.
2. Select up to eight rows and choose **Show selected images in Explorer**. Reading and preparing files runs in the background and can be stopped with the Wizard Stop button. Missing files or invalid WCS are reported individually.
3. In Explorer, choose **Source colors** or **Grayscale** under **Wizard images** and adjust **Opacity**. Use an individual archive layer to isolate that source, or **Image Wizard: All** to compare sources. **Off** hides image pixels while retaining coverage outlines.
4. Save the project to preserve the selected image keys, mode and opacity. On reopening, available local files are loaded again without network requests; missing files are reported. Opening an older project clears prior overlays.

These are display comparisons: each image is independently stretched, sampled to at most 1200 pixels per side, and projected by its celestial WCS into a bounded preview raster. Invalid or missing pixels stay transparent. Images are composited in selection/list order; later images appear above earlier ones. Source colors identify archives, not physical colors. The preview does not match epochs, instrumental response or resolution, and it is not a calibrated flux comparison. Use Color Composer for exported RGB/LRGB images.

## Version 2.1.0: layers, portable projects and resolution matching

### Control individual Explorer images

1. Download images in Image Wizard, select up to eight, and click **Show selected images in Explorer**.
2. Select Grayscale or Source colors under Wizard images.
3. Click **Image layers...**, select an image, set Visible and Opacity, then click Apply.
4. Use Lower or Raise to change the drawing order. The list runs from bottom layer to top layer. The top image can cover images beneath it.
5. Save the project to retain layer order, visibility and opacity. Global opacity multiplies each image's opacity. Hidden images keep their coverage outlines.

### Move a project to another folder or computer

1. Finish downloading the images referenced by your project.
2. Click **Export portable** in Image Wizard and choose a parent folder.
3. The app creates a new Hubble_<target>_<timestamp> folder with project.json, data/, results/ and manifest.json.
4. Copy the entire folder to the new location. Open its project.json using **Open project**.

The bundle includes every referenced local FITS image, including unused downloaded catalog records and aligned RGB/L images. Repeated references are copied once. Large projects can therefore need substantial disk space. Missing referenced files stop export with a message. Images are checked against SHA-256 checksums when opened. Keep filenames and manifest.json intact. Network access is unnecessary for bundled images; archive searches and new downloads still require it. Application dependencies must already be installed on the other computer. Original external preview exports are not bundled; rebuild/export them after opening. Regular Save project remains a lightweight JSON file referencing existing files.

### Match channel resolution

1. Assign R, G, B and optionally L.
2. Click **Resolution matching...** and enable matching.
3. Enter the estimated FWHM (full width at half maximum) in arcseconds for each assigned channel, then Save settings.
4. Click **Build RGB / LRGB** again.

The sharpest channels are smoothed to the largest supplied FWHM, after WCS alignment and before stretching. The added Gaussian width is the square root of the difference of squared FWHMs. The broadest channel needs no additional smoothing. Settings are saved in projects; input and target FWHM are recorded in alignment provenance and the output PSFFWHM FITS card records the assumed target.

This optional tool uses a circular Gaussian approximation and local WCS pixel scales. It does not measure a telescope PSF, account for spatially varying PSFs or interpolation blur, calibrate fluxes across instruments, or perform deconvolution. It is intended for visual comparisons on small, approximately orthogonal sky grids. Original FITS files remain unchanged. Missing pixels stay missing; values near masked edges use normalized valid-pixel weights. Requested kernels above 64 pixels sigma are rejected to bound memory use. Disable matching to retain the original workflow.
