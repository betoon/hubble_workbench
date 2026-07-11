# Observatory Explorer Test Guide

This is a quick click-by-click guide for testing the newer Observatory Explorer, sensor coverage, and mixed-sensor RGB planning tools.

## Good Targets To Try

Start with targets that often have useful Hubble and/or JWST coverage:

- `M51`
- `M16`
- `NGC 3324`
- `NGC 6302`
- `Stephan's Quintet`
- `Carina Nebula`

For early testing, use `M51` or `NGC 6302` first. They are usually easier than planets or very sparse targets.

## Basic Setup

1. Launch Hubble Workbench with `launch_hubble_workbench.bat`.
2. Open the **MAST Browser** tab.
3. Set **Telescope** to **Both HST + JWST** when you want to test mixed-source tools.
4. Enter a target, for example `M51`.
5. Set **Radius** to `0.05 deg` to start.
6. Click **Search MAST**.
7. Wait for the observation list to fill.
8. Click **Get All Products**.
9. Wait for the product list to fill.

Why this matters: most of the new sensor and mixed-RGB tools work best after both observations and products are loaded.

## Test 1: Observatory Overview

1. Click the **Observatory Explorer** tab.
2. Click **Analyze Current Search**.
3. Read the **Explorer Report** on the left.
4. Look for summaries by mission, instrument, wavelength bucket, and RGB readiness.
5. Click **Composition Strategy**.
6. Click **Image Readiness**.

Expected result: the report should explain what data is loaded, what looks promising, and what action to try next.

If the report says products are missing, go back to **MAST Browser** and click **Get All Products**.

## Test 2: Sky Mosaic And Coverage

1. Stay on **Observatory Explorer**.
2. Click **Build Sky Mosaic View**.
3. In the map controls, set **Layer** to **All active sources**.
4. Toggle **Best candidates only** on and off.
5. Set **Layer** to **Hubble / HST**.
6. Set **Layer** to **JWST**.
7. Click **Coverage Summary**.

Expected result: the map should draw observation centers. Hubble and JWST coverage boxes may appear when enough coordinate-bearing rows exist. The report should describe overlap when it can estimate one.

Useful follow-up:

1. Click **Search Wider Radius** if the map is sparse.
2. Click **Find Better Sources** if RGB coverage looks incomplete.
3. Click **Overlap Candidates** to list promising Hubble/JWST overlap rows.
4. Click **Export Overlap** if you want a CSV record of the candidates.

## Test 3: Sensor And Instrument Coverage

1. On **Observatory Explorer**, find the **Sensor / Instrument Coverage** section.
2. Click **Refresh Sensors**.
3. Click **Sensor Report**.
4. Click **Rank Sensors**.
5. Review the sensor list below the buttons.
6. Change **Sensor filter** to a sensor such as **WFC3 UVIS**, **ACS WFC**, **NIRCam**, or **MIRI**.
7. Click **Build Sky Mosaic View** again.

Expected result: the sensor list should show which instruments have usable data. Changing the sensor filter should narrow the mosaic view to that sensor family.

To test selection:

1. Click a sensor row in the sensor list.
2. Click **Show Selected Sensor**.
3. Double-click a sensor row as a shortcut.
4. Click **Use Best Sensor** to let the app choose the best-ranked sensor.

Expected result: the mosaic and report should focus on the selected sensor.

## Test 4: Single-Sensor RGB Planning

Use this when you want an RGB set from one instrument/sensor family.

1. Load products first from **MAST Browser** using **Get All Products**.
2. Go to **Observatory Explorer**.
3. Click **Rank Sensors**.
4. Click **Use Best Sensor**.
5. Click **Sensor RGB Plan**.
6. Read the report for blue, green, and red channel candidates.
7. Click **Prepare Sensor RGB**.

Expected result: the app switches back to **MAST Browser** and selects the best RGB picks for that sensor.

Then:

1. Open the **RGB Picker** sub-tab on the right side of **MAST Browser**.
2. Review the selected blue, green, and red rows.
3. Click **Download Selected RGB Channels**.
4. After download, use **Color Composer** to compose or inspect the channels.

If **Prepare Sensor RGB** says no complete RGB set is available, click **Sensor RGB Plan** and look for the missing color channel. Then try **Find Better Sources**, **Search Wider Radius**, or a different **Sensor filter**.

## Test 5: Mixed-Sensor RGB Planning

Use this when one sensor does not provide all three channels, or when you want a more complete image by combining sensors.

1. In **MAST Browser**, set **Telescope** to **Both HST + JWST**.
2. Search a target.
3. Click **Get All Products**.
4. Go to **Observatory Explorer**.
5. Click **Mixed RGB Plan**.
6. Click **Check Mixed Alignment**.
7. Click **Mixed Recipe**.
8. Click **Save Recipe**.
9. Click **Prepare Mixed RGB**.

Expected result: the app chooses blue, green, and red channels across available sensors, then switches back to **MAST Browser** with those products selected. The status line reports an alignment score.

Then:

1. Open **RGB Picker**.
2. Review the three selected channels.
3. Click **Download Selected RGB Channels**.
4. Compose the image in **Color Composer**.
5. Inspect the output carefully for channel misalignment, especially if the alignment score was low.

Important note: mixed-sensor images can be scientifically and visually useful, but they are more likely to need manual inspection. Different sensors may have different resolution, field of view, orientation, or coverage.

## Test 6: Marker-Based Product Lookup

Use this when the mosaic shows a promising observation point.

1. Go to **Observatory Explorer**.
2. Click **Build Sky Mosaic View**.
3. Click a marker on the map.
4. Confirm the selected marker is highlighted.
5. Click **Copy Marker Details** if you want to inspect the row text.
6. Click **Get Marker Products**.

Expected result: the app switches to product loading for the selected observation. This is useful when the map reveals a promising coverage area that the main product list did not emphasize.

## Test 7: Fast Completeness Check

1. Load products with **Get All Products** or **Find Better Sources**.
2. Click **Completeness Check**.
3. Read the checklist.

Expected result: the app reports whether it has direct FITS files, blue/green/red candidates, complete RGB sets, alignment confidence, enhanced products, and wider observation context.

If the checklist says something is missing:

- Missing products: click **Get All Products**.
- Missing channels: click **Find Better Sources**.
- Sparse coverage: click **Search Wider Radius**.
- Weak alignment: try **Prepare Sensor RGB** before **Prepare Mixed RGB**.

## Suggested Full Test Run

This is the best end-to-end path for testing the new features.

1. Open **MAST Browser**.
2. Set **Telescope** to **Both HST + JWST**.
3. Enter `M51`.
4. Set **Radius** to `0.05 deg`.
5. Click **Search MAST**.
6. Click **Get All Products**.
7. Open **Observatory Explorer**.
8. Click **Analyze Current Search**.
9. Click **Build Sky Mosaic View**.
10. Click **Sensor Report**.
11. Click **Rank Sensors**.
12. Click **Use Best Sensor**.
13. Click **Sensor RGB Plan**.
14. Click **Prepare Sensor RGB**.
15. Review the **RGB Picker**.
16. Return to **Observatory Explorer**.
17. Click **Mixed RGB Plan**.
18. Click **Check Mixed Alignment**.
19. Click **Mixed Recipe**.
20. Click **Save Recipe**.
21. Click **Prepare Mixed RGB**.
22. Review the **RGB Picker** again.
23. Click **Download Selected RGB Channels**.
24. Compose and inspect the result in **Color Composer**.

## What To Record While Testing

When something looks wrong, note these details:

- Target name
- Telescope setting
- Radius
- Which button you clicked
- Status message at the bottom of the panel
- Whether products were loaded first
- Whether the issue happened with **Sensor RGB** or **Mixed RGB**
- Alignment score from **Check Mixed Alignment**, if shown

Saved reports and recipes usually go into the app's logs/search output area. Use **Save Report**, **Save Project Plan**, **Save Plan**, and **Save Recipe** when you want files to compare between test runs.
## Debug Console

Use this while testing long searches, product downloads, sensor plans, and mixed RGB workflows.

1. Click the **Debug Console** tab.
2. Leave it open while you run **Search MAST**, **Get All Products**, **Find Better Sources**, **Prepare Sensor RGB**, or **Prepare Mixed RGB**.
3. Watch for started, progress, finished, warning, and error messages.
4. Click **Refresh From Debug File** to load the latest lines from `debug_hubble.txt`.
5. Click **Open Debug File** when you want the full debug log.
6. Click **Copy Test Snapshot** to copy target/search/product/sensor status in one report.
7. Click **Copy Bug Report** to copy the test snapshot plus the most useful recent console context.
8. Click **Copy Console** to copy everything visible, or **Copy Last Issue** to copy the most recent warning/error area.
9. Click **Save Console** if you want to save only what is visible in the console tab.

This tab is meant as a temporary cockpit view while the app is still growing. It does not replace the normal status messages, but it should make slow background work much easier to follow.
