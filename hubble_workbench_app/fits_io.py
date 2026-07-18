import shutil
import subprocess
import math
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image

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

