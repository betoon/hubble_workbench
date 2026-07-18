import shutil
import subprocess
import math
import warnings
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .paths import APP_DIR
from .settings import SETTINGS

_debug_log = lambda _message, *_args: None
_info_log = lambda _message, *_args: None
_warning_log = lambda _message, *_args: None


def configure_logging(debug_log=None, info_log=None, warning_log=None):
    global _debug_log, _info_log, _warning_log
    if debug_log is not None:
        _debug_log = debug_log
    if info_log is not None:
        _info_log = info_log
    if warning_log is not None:
        _warning_log = warning_log
    _debug_log("Checking optional astronomy imports")
    if MISSING_DEPS:
        _warning_log("Missing optional dependencies: %s", MISSING_DEPS)
    else:
        _info_log("Optional astronomy dependencies loaded successfully")


def optional_imports():
    _debug_log("Checking optional astronomy imports")
    missing = []
    try:
        from astropy.io import fits
    except Exception:
        fits = None
        missing.append("astropy")
    try:
        from astroquery.mast import Observations
    except Exception:
        Observations = None
        missing.append("astroquery")
    if missing:
        _warning_log("Missing optional dependencies: %s", missing)
    else:
        _info_log("Optional astronomy dependencies loaded successfully")
    return fits, Observations, missing


FITS, OBSERVATIONS, MISSING_DEPS = optional_imports()


def first_image_hdu(path):
    if FITS is None:
        raise RuntimeError("astropy is not installed.")
    with FITS.open(path, memmap=False) as hdul:
        best_header = None
        for hdu in hdul:
            data = getattr(hdu, "data", None)
            if data is None:
                continue
            arr = np.asarray(data)
            while arr.ndim > 2:
                arr = arr[0]
            if arr.ndim == 2 and arr.size:
                best_header = hdu.header
                return arr.astype(np.float64), dict(best_header)
    raise RuntimeError(f"No 2D image data found in {path}")


def _celestial_wcs(header):
    try:
        from astropy.wcs import WCS
        clean_header = FITS.Header()
        for key, value in dict(header).items():
            if str(key).upper() in ("", "COMMENT", "HISTORY"):
                continue
            try:
                clean_header[key] = value
            except Exception:
                continue
        wcs = WCS(clean_header, relax=True).celestial
    except Exception as exc:
        raise RuntimeError(f"FITS header has no usable celestial WCS: {exc}") from exc
    if wcs.pixel_n_dim != 2 or wcs.world_n_dim != 2 or not wcs.has_celestial:
        raise RuntimeError("FITS header has no usable two-dimensional celestial WCS.")
    return wcs


def _reproject_bilinear(data, source_wcs, output_wcs, shape, chunk_rows=256):
    """Reproject one array with bilinear interpolation and NaN outside its footprint."""
    height, width = shape
    source_height, source_width = data.shape
    output = np.full(shape, np.nan, dtype=np.float32)
    for y_start in range(0, height, chunk_rows):
        y_stop = min(height, y_start + chunk_rows)
        yy, xx = np.mgrid[y_start:y_stop, 0:width]
        world = output_wcs.pixel_to_world_values(xx, yy)
        source_x, source_y = source_wcs.world_to_pixel_values(*world)
        valid = (
            np.isfinite(source_x) & np.isfinite(source_y)
            & (source_x >= 0) & (source_y >= 0)
            & (source_x <= source_width - 1) & (source_y <= source_height - 1)
        )
        if not valid.any():
            continue
        safe_x = np.where(valid, source_x, 0)
        safe_y = np.where(valid, source_y, 0)
        x0 = np.floor(safe_x).astype(np.int64)
        y0 = np.floor(safe_y).astype(np.int64)
        x0 = np.clip(x0, 0, source_width - 1)
        y0 = np.clip(y0, 0, source_height - 1)
        x1 = np.clip(x0 + 1, 0, source_width - 1)
        y1 = np.clip(y0 + 1, 0, source_height - 1)
        dx = source_x - x0
        dy = source_y - y0
        values = (
            data[y0, x0] * (1 - dx) * (1 - dy)
            + data[y0, x1] * dx * (1 - dy)
            + data[y1, x0] * (1 - dx) * dy
            + data[y1, x1] * dx * dy
        )
        block = output[y_start:y_stop]
        block[valid] = values[valid].astype(np.float32)
    return output


def wcs_align_fits_channels(paths, max_output_pixels=16_000_000):
    """Place FITS channels on a shared union sky grid using their celestial WCS."""
    if FITS is None:
        raise RuntimeError("astropy is not installed.")
    sources = []
    for path in paths:
        data, header = first_image_hdu(path)
        finite = np.isfinite(data)
        if finite.any():
            zero_fraction = float(np.count_nonzero(finite & (data == 0)) / finite.sum())
            if zero_fraction >= 0.02 and np.any(finite & (data != 0)):
                data = np.where(data == 0, np.nan, data)
        sources.append({"path": str(path), "data": data, "header": header, "wcs": _celestial_wcs(header)})
    if len(sources) < 2:
        raise RuntimeError("At least two FITS channels are required for WCS alignment.")

    reference_wcs = sources[0]["wcs"]
    reference_points = []
    for source in sources:
        height, width = source["data"].shape
        corners_x = np.array([-0.5, width - 0.5, width - 0.5, -0.5])
        corners_y = np.array([-0.5, -0.5, height - 0.5, height - 0.5])
        world = source["wcs"].pixel_to_world_values(corners_x, corners_y)
        ref_x, ref_y = reference_wcs.world_to_pixel_values(*world)
        finite = np.isfinite(ref_x) & np.isfinite(ref_y)
        reference_points.extend(zip(ref_x[finite], ref_y[finite]))
    if len(reference_points) < 4:
        raise RuntimeError("The FITS footprints could not be transformed onto a shared sky grid.")

    xs = np.array([point[0] for point in reference_points])
    ys = np.array([point[1] for point in reference_points])
    x_min, x_max = int(np.floor(xs.min())), int(np.ceil(xs.max()))
    y_min, y_max = int(np.floor(ys.min())), int(np.ceil(ys.max()))
    width, height = x_max - x_min, y_max - y_min
    if width <= 0 or height <= 0:
        raise RuntimeError("The shared WCS footprint has invalid dimensions.")
    output_wcs = deepcopy(reference_wcs)
    output_wcs.wcs.crpix -= np.array([x_min, y_min], dtype=float)
    full_resolution_shape = (height, width)
    scale_factor = 1.0
    if width * height > int(max_output_pixels):
        scale_factor = math.sqrt((width * height) / max(1, int(max_output_pixels))) * 1.001
        while math.ceil(width / scale_factor) * math.ceil(height / scale_factor) > int(max_output_pixels):
            scale_factor *= 1.01
        if output_wcs.wcs.has_cd():
            output_wcs.wcs.cd *= scale_factor
        else:
            output_wcs.wcs.cdelt *= scale_factor
        output_wcs.wcs.crpix = 0.5 + (output_wcs.wcs.crpix - 0.5) / scale_factor
        width = max(1, int(math.ceil(width / scale_factor)))
        height = max(1, int(math.ceil(height / scale_factor)))
    shape = (height, width)
    aligned = [
        _reproject_bilinear(source["data"], source["wcs"], output_wcs, shape)
        for source in sources
    ]
    masks = [np.isfinite(channel) for channel in aligned]
    union = np.logical_or.reduce(masks)
    overlap = np.logical_and.reduce(masks)
    union_pixels = int(union.sum())
    overlap_pixels = int(overlap.sum())
    output_header = dict(output_wcs.to_header(relax=True))
    headers = [dict(output_header) for _source in sources]
    metadata = {
        "mode": "celestial WCS union",
        "output_shape": shape,
        "full_resolution_shape": full_resolution_shape,
        "pixel_scale_factor": scale_factor,
        "source_shapes": [source["data"].shape for source in sources],
        "coverage_fractions": [float(mask.sum() / max(1, union_pixels)) for mask in masks],
        "overlap_fraction": float(overlap_pixels / max(1, union_pixels)),
        "union_pixels": union_pixels,
        "overlap_pixels": overlap_pixels,
    }
    return aligned, headers, metadata


def _background_plane(reference, source, overlap, gain):
    """Fit a conservative offset plane from source to reference in their overlap."""
    yy, xx = np.where(overlap)
    if xx.size < 20:
        offset = float(np.nanmedian(reference[overlap] - gain * source[overlap])) if xx.size else 0.0
        return (offset, 0.0, 0.0), (offset, offset)
    step = max(1, int(math.ceil(xx.size / 200_000)))
    yy = yy[::step]
    xx = xx[::step]
    height, width = reference.shape
    x_norm = (xx - (width - 1) / 2.0) / max(1.0, width / 2.0)
    y_norm = (yy - (height - 1) / 2.0) / max(1.0, height / 2.0)
    difference = reference[yy, xx].astype(np.float64) - gain * source[yy, xx].astype(np.float64)
    design = np.column_stack([np.ones(xx.size), x_norm, y_norm])
    coefficients, *_ = np.linalg.lstsq(design, difference, rcond=None)
    residual = difference - design @ coefficients
    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    if mad > np.finfo(float).eps:
        keep = np.abs(residual - median) <= 4.0 * 1.4826 * mad
        if keep.sum() >= 20:
            coefficients, *_ = np.linalg.lstsq(design[keep], difference[keep], rcond=None)
    fitted = design @ coefficients
    low, high = np.percentile(fitted, [2, 98])
    padding = max(float(high - low) * 0.25, np.finfo(float).eps)
    return tuple(float(value) for value in coefficients), (float(low - padding), float(high + padding))


def stack_fits_exposures(paths, output_path, weights=None, max_output_pixels=8_000_000, sigma=6.0, feather_pixels=12):
    """WCS-align and robustly combine repeated exposures from one filter."""
    paths = list(paths or [])
    if not paths:
        raise RuntimeError("No FITS exposures were provided for stacking.")
    if len(paths) == 1:
        raise RuntimeError("At least two FITS exposures are required for stacking.")
    aligned, headers, alignment = wcs_align_fits_channels(paths, max_output_pixels=max_output_pixels)
    cube = np.stack(aligned).astype(np.float32)
    medians = []
    for layer in cube:
        finite = layer[np.isfinite(layer)]
        medians.append(float(np.nanmedian(finite)) if finite.size else 0.0)
    reference_median = medians[0]
    reference = cube[0]
    background_offsets = [0.0]
    background_planes = [(0.0, 0.0, 0.0)]
    background_plane_limits = [(0.0, 0.0)]
    photometric_gains = [1.0]
    for index in range(1, len(cube)):
        overlap = np.isfinite(reference) & np.isfinite(cube[index])
        if overlap.sum() >= 100:
            source_all = cube[index][overlap].astype(np.float64)
            reference_all = reference[overlap].astype(np.float64)
            source_low, source_high = np.nanpercentile(source_all, [5, 95])
            reference_low, reference_high = np.nanpercentile(reference_all, [5, 95])
            stable = (
                (source_all >= source_low) & (source_all <= source_high)
                & (reference_all >= reference_low) & (reference_all <= reference_high)
            )
            source_values = source_all[stable]
            reference_values = reference_all[stable]
            variance = float(np.var(source_values)) if source_values.size else 0.0
            if source_values.size >= 100 and variance > np.finfo(float).eps:
                covariance = float(np.mean((source_values - source_values.mean()) * (reference_values - reference_values.mean())))
                gain = min(4.0, max(0.25, covariance / variance))
            else:
                gain = 1.0
            background_stable = (
                stable
                & (source_all <= np.nanpercentile(source_values, 45))
                & (reference_all <= np.nanpercentile(reference_values, 45))
            )
            stable_overlap = overlap.copy()
            overlap_y, overlap_x = np.where(overlap)
            stable_overlap[overlap_y, overlap_x] = background_stable
            plane, plane_limits = _background_plane(reference, cube[index], stable_overlap, gain)
            offset = plane[0]
        else:
            gain = 1.0
            offset = reference_median - gain * medians[index]
            plane = (offset, 0.0, 0.0)
            plane_limits = (offset, offset)
        if plane[1] or plane[2]:
            height, width = cube[index].shape
            y_norm = (np.arange(height, dtype=np.float32) - (height - 1) / 2.0) / max(1.0, height / 2.0)
            x_norm = (np.arange(width, dtype=np.float32) - (width - 1) / 2.0) / max(1.0, width / 2.0)
            correction = plane[0] + plane[1] * x_norm[None, :] + plane[2] * y_norm[:, None]
            correction = np.clip(correction, plane_limits[0], plane_limits[1])
            cube[index] = cube[index] * gain + correction
        else:
            cube[index] = cube[index] * gain + offset
        photometric_gains.append(gain)
        background_offsets.append(offset)
        background_planes.append(plane)
        background_plane_limits.append(plane_limits)

    if weights is None:
        weights = np.ones(len(paths), dtype=np.float32)
    weights = np.asarray(weights, dtype=np.float32)
    if weights.size != len(paths):
        raise RuntimeError("Exposure weights must match the number of FITS files.")
    weights = np.where(np.isfinite(weights) & (weights > 0), weights, 1.0)
    valid = np.isfinite(cube)
    feather_layers = []
    for mask in valid:
        if feather_pixels and feather_pixels > 0:
            mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
            feather = np.asarray(mask_image.filter(ImageFilter.GaussianBlur(radius=float(feather_pixels))), dtype=np.float32) / 255.0
            feather *= mask
            feather_layers.append(np.maximum(feather, np.where(mask, 0.02, 0.0)))
        else:
            feather_layers.append(mask.astype(np.float32))
    feather_cube = np.stack(feather_layers)
    weight_cube = weights[:, None, None] * feather_cube
    keep = valid.copy()
    if len(paths) >= 3:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
            median_image = np.nanmedian(cube, axis=0)
            mad = np.nanmedian(np.abs(cube - median_image), axis=0)
        threshold = np.maximum(float(sigma) * 1.4826 * mad, np.finfo(np.float32).eps)
        keep &= np.abs(cube - median_image) <= threshold
    effective_weights = np.where(keep, weight_cube, 0.0)
    numerator = np.nansum(np.where(keep, cube * weight_cube, 0.0), axis=0)
    denominator = effective_weights.sum(axis=0)
    stacked = np.divide(
        numerator,
        denominator,
        out=np.full(numerator.shape, np.nan, dtype=np.float32),
        where=denominator > 0,
    ).astype(np.float32)
    coverage = keep.sum(axis=0).astype(np.uint16)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = FITS.Header()
    for key, value in headers[0].items():
        try:
            header[key] = value
        except Exception:
            continue
    header["NSTACK"] = (len(paths), "Number of WCS-aligned exposures")
    header["STACKMTH"] = ("SIGCLIP", "Weighted sigma-clipped mean")
    hdul = FITS.HDUList([
        FITS.PrimaryHDU(stacked, header=header),
        FITS.ImageHDU(coverage, name="COVERAGE"),
    ])
    hdul.writeto(output_path, overwrite=True)
    metadata = dict(alignment)
    metadata.update({
        "output_path": str(output_path),
        "exposure_count": len(paths),
        "weights": [float(value) for value in weights],
        "background_medians": medians,
        "background_offsets": background_offsets,
        "background_planes": [list(values) for values in background_planes],
        "background_plane_limits": [list(values) for values in background_plane_limits],
        "photometric_gains": photometric_gains,
        "rejected_samples": int((valid & ~keep).sum()),
        "max_coverage": int(coverage.max()) if coverage.size else 0,
        "feather_pixels": int(feather_pixels),
    })
    return output_path, metadata


def find_fits_liberator_cli():
    configured = str(SETTINGS.get("fits_liberator_cli_path", "")).strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend([
        APP_DIR / "fitscli" / "win" / "fits.exe",
        APP_DIR / "fitscli" / "fits.exe",
        APP_DIR.parent.parent / "github" / "fits-liberator-gui-master" / "fitscli" / "win" / "fits.exe",
        APP_DIR.parent.parent / "github" / "fits-liberator-cli-master" / "fitscli.exe",
        APP_DIR.parent.parent / "github" / "fits-liberator-cli-master" / "fits.exe",
    ])
    found = shutil.which("fitscli") or shutil.which("fits")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def fits_liberator_stretch_args(stretch, low, high, gamma=1.0, asinh_strength=12.0):
    stretch = (stretch or "linear").lower()
    if stretch == "sqrt":
        return "pow", "0.5", "100"
    if stretch == "pow":
        return "pow", f"{max(0.05, float(gamma)):.6g}", "100"
    if stretch == "log":
        return "log", "0.5", "100"
    if stretch == "asinh":
        return "asinh", "0.5", f"{max(0.1, float(asinh_strength)):.6g}"
    return "linear", "0.5", "100"


def read_liberated_channel(path):
    with Image.open(path) as image:
        arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    if arr.dtype == np.uint16:
        return (arr.astype(np.float32) / 65535.0).clip(0, 1)
    if arr.dtype == np.uint8:
        return (arr.astype(np.float32) / 255.0).clip(0, 1)
    arr = arr.astype(np.float32)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, dtype=np.float32)
    lo = np.nanmin(arr[finite])
    hi = np.nanmax(arr[finite])
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.float32)
    return ((arr - lo) / (hi - lo)).clip(0, 1).astype(np.float32)


def run_fits_liberator_channel(cli_path, input_path, output_path, low, high, stretch, gamma=1.0, asinh_strength=12.0):
    cli_stretch, exponent, scaled_peak = fits_liberator_stretch_args(stretch, low, high, gamma, asinh_strength)
    command = [
        str(cli_path),
        "--infile", str(input_path),
        "--outfile", str(output_path),
        "--stretch", cli_stretch,
        "--backgroundlevel", f"{float(low):.12g}",
        "--peaklevel", f"{float(high):.12g}",
        "--scaledpeaklevel", str(scaled_peak),
        "--exponent", str(exponent),
        "--depth", "16",
        "--outformat", "1",
        "--quiet", "1",
        "--undefined", "0",
        "--fastmode", "0",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=900)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"FITS Liberator failed for {Path(input_path).name}: {detail or completed.returncode}")
    if not Path(output_path).exists():
        raise RuntimeError(f"FITS Liberator did not create {Path(output_path).name}")
    return read_liberated_channel(output_path)

