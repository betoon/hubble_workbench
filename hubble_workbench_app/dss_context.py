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
