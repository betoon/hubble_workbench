import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DSS_JPEG_ENDPOINT = "https://gsss.stsci.edu/webservices/dssjpg/dss.svc/GetImage"


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
