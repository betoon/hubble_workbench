# Space Telescope Workbench - Beginner User Manual

This guide is written for normal use, not astronomy experts. The basic idea is:

1. Pick a telescope.
2. Pick a target.
3. Search for observations.
4. Find useful image products.
5. Download FITS files.
6. Preview or combine them into a color image.

The workbench uses MAST, the public archive for Hubble and James Webb data.

## Quick Start: The Easy Button

Use this when you want the app to do most of the work.

1. Open `launch_hubble_workbench.bat`.
2. Go to the **MAST Browser** tab.
3. Choose a telescope:
   - **Hubble / HST** for Hubble Space Telescope.
   - **James Webb / JWST** for James Webb Space Telescope.
   - **Both HST + JWST** if you want both.
4. Pick a target from **Target Gallery**.
5. Click **Easy RGB Image**.
6. Wait. This can take several minutes.
7. When it finishes, the app moves to **Color Composer** and shows the image.
8. Click **Save PNG/TIFF + Notes** when you like the result.
9. Optional: open **Hydrogen Enhance**, click **Use Final Composite**, choose a color preset, and compare the original with the enhanced version.

If Easy RGB fails, try a different target or use a smaller/larger radius.

## Hydrogen Enhance Tab

Use this after creating a final RGB image in **Color Composer**. Click **Use Final Composite**, then adjust glow strength, H-II region size, stretch, sky level, and color preset. The side-by-side view compares the source and enhanced image; **H-II Mask** shows exactly which structures drive the effect. Click the displayed image to choose a background color when border masking needs help.

Choose **Save Enhanced PNG + TIFF** to save an 8-bit PNG, a 16-bit RGB TIFF, and the enhancement mask in `outputs/`. This is a visual hydrogen/H-II enhancement, not a calibrated scientific H-alpha measurement.

## Setup Tab

The **Setup** tab checks whether the astronomy tools are installed.

### Refresh Status

Checks whether required packages are available:

- `astroquery` searches and downloads from MAST.
- `astropy` reads FITS files.
- `numpy` handles image data.
- `Pillow` saves and displays images.

If something is missing, run:

`install_dependencies.bat`

Then restart the app.

### Open Downloads Folder

Opens the folder where downloaded FITS files are stored.

### Open Outputs Folder

Opens the folder where PNG/TIFF images are saved.

## MAST Browser Tab

This is where you search for telescope data.

### Telescope

Choose which archive collection to search.

- **Hubble / HST**: Hubble images.
- **James Webb / JWST**: Webb images.
- **Both HST + JWST**: searches both, but can return more results.

For beginners, choose one telescope at a time.

### Target Gallery

A list of interesting objects. Pick one, then click **Use Target**.

Examples:

- **M16 - Eagle Nebula**
- **M51 - Whirlpool Galaxy**
- **Carina Nebula - Cosmic Cliffs**
- **Stephan's Quintet**

### Target

The object name to search for.

Examples:

- `M16`
- `M51`
- `NGC 3324`
- `Stephan's Quintet`
- `Jupiter`
- `Uranus`

For fixed deep-sky objects, the app searches around the object's sky coordinates.

For planets and other solar-system targets, the app also tries a MAST target-name search. That matters because planets move across the sky, so a normal fixed-coordinate search can miss JWST or Hubble observations even when the archive has them.

For planets, choose **James Webb / JWST** or **Both HST + JWST**, then enter the plain planet name, such as `Jupiter`, `Uranus`, or `Neptune`.

### Radius

How wide an area of sky to search around the target.

- `0.02 deg`: tight search, fewer results, faster.
- `0.05 deg`: good default.
- `0.10 deg`: wider search, more results.
- `0.5 deg`: very wide, can be slow and noisy.

If you get too many products, lower the radius. If you get too few, raise it.

### Search MAST

Searches the archive for observations matching your target and telescope.

After searching, observations appear in the left list.

### Easy RGB Image

The one-click workflow.

It searches, checks products, finds a blue/green/red set, downloads it, and creates a color image.

Use this first when learning the app.

### Search HLA Fallback

Hubble-only fallback search. Use this if normal Hubble MAST search has trouble.

It does not work for JWST.

### Get Products

After selecting an observation on the left, click **Get Products**.

This fills the Products list on the right.

### Download Selected Products

Downloads whatever products are selected in the Products list.

## Observations List

The left list shows observations found by MAST.

A line may include:

- Telescope collection, such as `HST` or `JWST`.
- Observation ID.
- Instrument.
- Filters.
- Exposure time.

Click one observation, then click **Get Products**.

## Products Tab

The Products tab can contain many files. The filters help reduce clutter.

### Direct FITS only

Shows files that are actual FITS images.

Keep this checked most of the time.

### Hide spectra

Hides spectra, grisms, prisms, and other non-image products.

Keep this checked when making pictures.

### RGB filters only

Shows products whose filters are useful for color images.

This is very helpful for JWST, because product lists can be huge.

### Complete RGB sets only

Shows only products that belong to a full blue/green/red set.

This is the easiest manual filter. Turn this on when the product list is overwhelming.

### Select Best RGB Products

Automatically selects the best blue, green, and red products from the product list.

After clicking it, you can click **Download Selected Products**.

## RGB Picker Tab

The RGB Picker organizes products into color channels.

### Blue / Green / Red columns

Each column lists products that look useful for that color channel.

For Hubble:

- Blue often uses filters like `F435W`, `F438W`, `F475W`.
- Green often uses `F555W`, `F606W`, `F502N`.
- Red often uses `F814W`, `F850LP`, `F658N`.

For JWST:

- Blue often uses shorter infrared filters like `F090W`, `F115W`, `F150W`.
- Green often uses middle filters like `F200W`, `F277W`, `F335M`.
- Red often uses longer filters like `F356W`, `F444W`, `F770W`.

JWST color is usually false color because Webb sees infrared.

### Suggested RGB Sets

The app looks for groups that contain a blue, green, and red product.

### Use Best Set

Selects the best suggested RGB set.

### Use Suggested Set

Uses the set you selected in the Suggested RGB Sets list.

### Download RGB Set

Downloads the selected blue, green, and red products.

### Copy RGB Picks

Copies the selected RGB product details to the clipboard.

## FITS Preview / Convert Tab

Use this to inspect one FITS file.

### Choose FITS

Pick one downloaded FITS file.

### Stretch

Controls how the brightness is mapped for viewing.

- **asinh**: good default for astronomy images.
- **sqrt**: can brighten faint details.
- **log**: can reveal very faint structures but may look harsh.

### Preview

Loads the FITS file and displays it.

The display is scaled to fit the app window. The status line shows the real pixel size.

### Save PNG/TIFF

Saves a preview image from the FITS file.

## Color Composer Tab

This creates a color RGB image from three FITS files.

### Choose Red / Green / Blue

Pick one FITS file for each color channel.

If you used **Download RGB Set**, use **Load Latest RGB Set** to fill these automatically.

### Load Latest RGB Set

Finds the most recent downloaded RGB set and loads it.

### Stretch

Controls brightness mapping for all three channels.

Recommended starting point: **asinh**.

### Auto compose

When checked, the app composes automatically after loading an RGB set.

### Compose RGB

Builds the color image.

### Save PNG/TIFF + Notes

Saves:

- PNG image.
- TIFF image.
- Notes file with processing settings and filter information.

### Open Latest Output

Opens the most recently saved output image.

### Save Project / Open Project

Saves or loads your current channel choices and processing settings.

## Color Composer Settings

### Black

Raises the black point. This darkens the background and removes haze.

Too much black can erase faint nebula or galaxy detail.

### Bright

Raises or lowers overall brightness.

### Contrast

Increases separation between dark and bright areas.

Higher contrast can make details pop, but can also crush shadows.

### Saturation

Controls color intensity.

JWST images often benefit from careful saturation because false color can get strong quickly.

### Red / Green / Blue

Adjusts the strength of each color channel.

Use these if the image looks too red, green, or blue.

### Presets

Quick processing styles:

- **Natural**: balanced starting point.
- **High Contrast**: stronger structure.
- **Nebula**: colorful and punchy.
- **Galaxy**: gentler color balance.
- **Soft Stretch**: lower contrast, smoother look.

### Show tuned image

When checked, shows your processed/tuned result.

When unchecked, shows the base composite.

### Composite Size

Controls how the app handles channels with different dimensions.

- **Largest channel**: highest output size. Smaller channels are upscaled.
- **Smallest channel**: safest alignment. Larger channels are downscaled.

For highest resolution, use **Largest channel**.

### Zoom

Controls on-screen viewing zoom only.

It does not change the saved image size.

## Recommended Beginner Workflows

### Easiest JWST Workflow

1. Go to **MAST Browser**.
2. Choose **James Webb / JWST**.
3. Pick a JWST target from **Target Gallery**.
4. Click **Easy RGB Image**.
5. Wait for the app to finish.
6. In **Color Composer**, adjust presets and sliders.
7. Save PNG/TIFF + Notes.

### Manual JWST Workflow

1. Choose **James Webb / JWST**.
2. Pick a target and click **Use Target**.
3. Click **Search MAST**.
4. Select an observation.
5. Click **Get Products**.
6. Check **Complete RGB sets only**.
7. Click **Select Best RGB Products**.
8. Click **Download Selected Products**.
9. Go to **Color Composer**.
10. Click **Load Latest RGB Set**.
11. Set **Composite Size** to **Largest channel**.
12. Click **Compose RGB**.
13. Save PNG/TIFF + Notes.

### Manual Hubble Workflow

1. Choose **Hubble / HST**.
2. Pick a target such as `M16`, `M51`, or `M101`.
3. Click **Search MAST**.
4. Select an observation.
5. Click **Get Products**.
6. Use **RGB Picker** or **Complete RGB sets only**.
7. Download the selected products.
8. Compose in **Color Composer**.

## Common Problems

### I selected an observation. What next?

Click **Get Products**.

### There are too many products.

Turn on:

- **Direct FITS only**
- **Hide spectra**
- **RGB filters only**
- **Complete RGB sets only**

Then click **Select Best RGB Products**.

### Easy RGB failed.

Try:

- A different target.
- A smaller radius, such as `0.02 deg`.
- A larger radius, such as `0.10 deg`.
- Manual workflow with **Complete RGB sets only**.

### The image looks low resolution.

The on-screen preview is scaled to fit the window.

Check the status line for actual pixel size. Use **Composite Size: Largest channel** for highest output size.

### The colors look strange.

That is normal, especially for JWST.

JWST sees infrared, so the app maps shorter infrared wavelengths to blue, middle wavelengths to green, and longer wavelengths to red.

### The image is too dark.

Try:

- Increase **Bright**.
- Use **Soft Stretch** or **Nebula** preset.
- Lower **Black**.

### The background is gray or washed out.

Try:

- Increase **Black** slowly.
- Increase **Contrast**.

### The image is too colorful.

Lower **Saturation**.

## Best First Targets

### JWST

- Carina Nebula - Cosmic Cliffs
- Southern Ring Nebula
- Stephan's Quintet
- Tarantula Nebula
- Pillars of Creation

### Hubble

- M16 - Eagle Nebula
- M51 - Whirlpool Galaxy
- M101 - Pinwheel Galaxy
- M57 - Ring Nebula
- NGC 6302 - Butterfly Nebula

## Plain-English Glossary

### FITS

The standard scientific image file format used by telescopes.

### MAST

The archive where Hubble and JWST data are stored.

### Observation

A telescope visit or dataset for a target.

### Product

A downloadable file from an observation.

### Filter

A wavelength band. Filters are used like color channels.

### RGB

Red, green, and blue combined into a color image.

### HST

Hubble Space Telescope.

### JWST

James Webb Space Telescope.

### i2d

A JWST combined image product. Usually a good choice.

### cal

A calibrated JWST product. Often useful.

### drc / drz

Hubble combined/drizzled image products. Usually good choices.

### raw / uncal

Raw data. Usually not the best first choice for making pretty images.
