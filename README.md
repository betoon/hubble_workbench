# Space Telescope Workbench

Space Telescope Workbench is a local starter tool for searching, downloading, previewing, and composing Hubble/HST and James Webb/JWST FITS image data from MAST.

## Start

Double-click:

```text
launch_hubble_workbench.bat
```

## Install astronomy dependencies

Double-click:

```text
install_dependencies.bat
```

Then restart the workbench.

The required packages are:

- astroquery
- astropy
- numpy
- Pillow
- tifffile

## Workflow

For a slower, beginner-friendly walkthrough of every button and setting, see:

`BEGINNER_USER_MANUAL.md`

For testing the newer Observatory Explorer, sensor coverage, sky mosaic, and mixed-sensor RGB tools, see:

`OBSERVATORY_EXPLORER_TEST_GUIDE.md`

1. Open **MAST Browser**.
2. Choose **Hubble / HST**, **James Webb / JWST**, or **Both HST + JWST**.
3. Search for a target such as `M51`, `NGC 6302`, `M16`, `NGC 3324`, or `Stephan's Quintet`.
4. For the guided workflow, choose **Easy High Quality**. It searches for strong RGB-ready products, prefers drizzled/mosaic files, downloads extra useful products for later, composes in high-quality mode, and saves PNG/TIFF/notes.
5. After the image opens in **Color Composer**, try the automatic look previews: Natural, Nebula, High Contrast, and Soft Stretch.
   The **Blue/Pink Nebula** preset is useful for dark dust clouds with red emission and cyan/blue highlight glow.
6. To emphasize compact hydrogen-rich structures in the finished image, open **Hydrogen Enhance** and choose **Use Final Composite**. Review the H-II mask before saving.
7. For manual work, select an observation, choose **Get Products**, download selected products, then assign FITS files in **Color Composer**.
8. Prefer science-ready products when available, especially Hubble `DRC`/`DRZ` or JWST `I2D`/`CAL` FITS files.

## Folder layout

- `downloads/` stores downloaded Hubble/JWST products.
- `outputs/` stores PNG/TIFF exports.
- `notes/` stores processing notes for RGB composites.

## Notes

Space telescope FITS processing can be tricky. Different filters and products may have different image sizes, orientations, or artifacts. This workbench keeps the process simple and automatic: it stretches each channel, resizes channels to match, and combines them into RGB.

Some Hubble detector products include black no-data gaps or a rotated detector footprint. In **Color Composer**, use **Presentation cleanup**, **Straighten**, and **Auto crop black border** to make cleaner PNG presentation exports. The cleanup improves the visible presentation image; it does not create real telescope data where the detector did not record any.

For multi-exposure RGB sets, **Mosaic coverage** defaults to **Full mosaic** so recorded sky is not silently discarded. Use **Stack Coverage Report** before choosing **Shared exposure overlap**; shared mode can create a cleaner central image but may remove most of a low-overlap field.

**Hydrogen Enhance** is a visual H-II/H-alpha proxy derived from RGB structure. It is intended for artistic enhancement and inspection, not calibrated narrowband measurement.
