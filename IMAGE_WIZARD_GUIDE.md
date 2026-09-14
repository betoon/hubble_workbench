# Image Wizard

Open **Image Wizard** to find, inspect and combine public astronomy images.

1. Choose a source and target. Names such as M51 work for most archives; decimal RA, Dec also works. Chandra uses curated target names, such as Orion, Cas A or Crab.
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
| Chandra | Curated OpenFITS images and energy bands | Named targets only, not a full Chandra archive search. Some targets have only one broad band. |
| Loaded Hubble/JWST | Current MAST Browser FITS products | Run the existing MAST search and load products first, then import them here. |

## Downloads and coverage

The wizard streams downloads and reports file progress. Verified cached files are reused. **Stop** interrupts at the next network/chunk or processing checkpoint; a pending request must finish or time out first. Partial files resume when the server provides a validator and supports byte ranges, otherwise restart safely. These controls apply to the Image Wizard; existing MAST buttons retain their own workflow.

Dashed coverage outlines show the requested cutout field, not a measured detector footprint. Solid archive polygons or downloaded FITS outlines show available boundaries. Actual common valid-pixel coverage is measured during alignment. Footprints can contain empty areas and do not guarantee useful signal. Very large alignment grids are reduced to four million pixels to limit memory use. Cropping removes exterior bounds; internal gaps remain missing.

Automatic colors map longer wavelengths to red and shorter wavelengths to blue. Cross-source assignments are manual and produce display composites, not calibrated photometry. Different resolutions, epochs and instrumental artifacts still require judgment. A project can be reopened offline while its downloaded and aligned files remain in their saved locations. SkyView download URLs are temporary; repeat Find images if an uncached old URL has expired.

Archive references: [Pan-STARRS](https://spacetelescope.github.io/mast_notebooks/notebooks/PanSTARRS/PS1_image/PS1_image.html), [SkyView](https://skyview.gsfc.nasa.gov/), [IRSA SIA](https://irsa.ipac.caltech.edu/ibe/sia.html), [Chandra OpenFITS](https://www.chandra.harvard.edu/photo/openFITS/xray_data.html). Preserve archive acknowledgments when sharing images.
