import shutil
import subprocess
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

