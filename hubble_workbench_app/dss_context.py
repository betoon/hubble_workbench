import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DSS_JPEG_ENDPOINT = "https://gsss.stsci.edu/webservices/dssjpg/dss.svc/GetImage"
DSS_FITS_ENDPOINT = "https://archive.stsci.edu/cgi-bin/dss_search"


def ra_degrees_to_hms(ra):
    total_seconds = (float(ra) % 360.0) * 240.0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def dec_degrees_to_dms(dec):
    dec = float(dec)
    if not -90.0 <= dec <= 90.0:
        raise ValueError("DSS declination must be between -90 and +90 degrees.")
    sign = "+" if dec >= 0 else "-"
    total_seconds = abs(dec) * 3600.0
    degrees = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{sign}{degrees:02d}:{minutes:02d}:{seconds:05.2f}"


def dss_jpeg_url(ra, dec, size_degrees, image_pixels=1200):
    ra = float(ra) % 360.0
    dec = float(dec)
    size = min(2.0, max(0.01, float(size_degrees)))
    if not -90.0 <= dec <= 90.0:
        raise ValueError("DSS declination must be between -90 and +90 degrees.")
    pixels = min(2400, max(256, int(image_pixels)))
    query = urllib.parse.urlencode({
        "POS": f"{ra:.8f},{dec:.8f}",
        "SIZE": f"{size:.6f}",
        "ISIZE": str(pixels),
        "ZOOM": "DYNAMIC",
        "DRAWDEBUG": "OFF",
    })
    return f"{DSS_JPEG_ENDPOINT}?{query}"


def dss_fits_url(ra, dec, size_degrees, survey="poss2ukstu_red"):
    size_arcminutes = min(120.0, max(1.0, float(size_degrees) * 60.0))
    query = urllib.parse.urlencode({
        "r": ra_degrees_to_hms(ra),
        "d": dec_degrees_to_dms(dec),
        "e": "J2000",
        "v": survey,
        "h": f"{size_arcminutes:.4f}",
        "w": f"{size_arcminutes:.4f}",
        "f": "fits",
        "c": "none",
        "fov": "NONE",
    })
    return f"{DSS_FITS_ENDPOINT}?{query}"


def download_dss_context(ra, dec, size_degrees, destination, timeout=90):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = dss_jpeg_url(ra, dec, size_degrees)
    request = urllib.request.Request(url, headers={"User-Agent": "Hubble-Workbench/2 DSS-context"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        content_type = str(response.headers.get("Content-Type", ""))
    if not data.startswith(b"\xff\xd8"):
        raise RuntimeError(f"DSS did not return a JPEG image (content type: {content_type or 'unknown'}).")
    destination.write_bytes(data)
    metadata = {
        "source": "Digitized Sky Survey via MAST/STScI",
        "service_url": url,
        "ra_degrees": float(ra) % 360.0,
        "dec_degrees": float(dec),
        "field_size_degrees": min(2.0, max(0.01, float(size_degrees))),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "image_path": str(destination),
        "usage_note": "Reference/framing image; not yet WCS-registered as a science layer.",
    }
    metadata_path = destination.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def download_dss_fits(ra, dec, size_degrees, destination, timeout=180):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = dss_fits_url(ra, dec, size_degrees)
    request = urllib.request.Request(url, headers={"User-Agent": "Hubble-Workbench/2 DSS-FITS"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        content_type = str(response.headers.get("Content-Type", ""))
    if not data.startswith(b"SIMPLE  ="):
        raise RuntimeError(f"DSS did not return a FITS image (content type: {content_type or 'unknown'}).")
    destination.write_bytes(data)
    metadata = {
        "source": "Digitized Sky Survey via MAST/STScI",
        "service_url": url,
        "format": "FITS",
        "survey": "poss2ukstu_red",
        "ra_degrees": float(ra) % 360.0,
        "dec_degrees": float(dec),
        "field_size_degrees": min(2.0, max(1.0 / 60.0, float(size_degrees))),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "fits_path": str(destination),
        "usage_note": "DSS reference FITS with archive WCS metadata; registration should be verified in FITS Preview.",
    }
    metadata_path = destination.with_suffix(".fits.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def load_dss_fits_overlay(path, max_dimension=1200):
    import numpy as np
    from PIL import Image
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(path, memmap=False) as hdul:
        hdu = next((item for item in hdul if getattr(item, "data", None) is not None), None)
        if hdu is None:
            raise ValueError("DSS FITS contains no image data.")
        data = np.asarray(hdu.data, dtype=np.float32)
        header = hdu.header.copy()
    while data.ndim > 2:
        data = data[0]
    if data.ndim != 2:
        raise ValueError("DSS FITS image is not two-dimensional.")
    height, width = data.shape
    wcs = WCS(header, relax=True).celestial
    if not wcs.has_celestial:
        raise ValueError("DSS FITS does not contain celestial WCS metadata.")
    pixel_corners = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=float)
    world_corners = wcs.all_pix2world(pixel_corners, 0)
    ras = [float(value) % 360.0 for value in world_corners[:, 0]]
    decs = [float(value) for value in world_corners[:, 1]]
    if max(ras) - min(ras) > 180.0:
        ras = [value + 360.0 if value < 180.0 else value for value in ras]
    finite = data[np.isfinite(data)]
    if not finite.size:
        raise ValueError("DSS FITS image contains no finite pixels.")
    low, high = np.percentile(finite, (1.0, 99.5))
    if high <= low:
        high = low + 1.0
    display = np.clip((data - low) / (high - low), 0.0, 1.0)
    display = np.nan_to_num(display, nan=0.0)
    display = np.flipud((display * 255.0).astype(np.uint8))
    image = Image.fromarray(display, mode="L").convert("RGBA")
    # After flipud, display corners are FITS corners 3, 2, 1, 0. Orient the
    # raster to the mosaic convention: RA grows rightward and Dec grows upward.
    top_left_ra, top_right_ra = ras[3], ras[2]
    top_dec = (decs[3] + decs[2]) / 2.0
    bottom_dec = (decs[0] + decs[1]) / 2.0
    if top_right_ra < top_left_ra:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if top_dec < bottom_dec:
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    image.putalpha(150)
    if max(image.size) > max_dimension:
        scale = max_dimension / max(image.size)
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    return {
        "image": image,
        "bounds": (min(ras), max(ras), min(decs), max(decs)),
        "corners": list(zip(ras, decs)),
        "shape": (height, width),
    }
