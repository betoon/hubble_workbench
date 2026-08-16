import csv
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PS1_FILENAMES_ENDPOINT = "https://ps1images.stsci.edu/cgi-bin/ps1filenames.py"
PS1_FITSCUT_ENDPOINT = "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"
PS1_PIXEL_SCALE_ARCSEC = 0.25


def panstarrs_filenames_url(ra, dec, filters="giy"):
    ra = float(ra) % 360.0
    dec = float(dec)
    if not -90.0 <= dec <= 90.0:
        raise ValueError("Pan-STARRS declination must be between -90 and +90 degrees.")
    filters = "".join(token for token in str(filters).lower() if token in "grizy") or "giy"
    query = urllib.parse.urlencode({
        "ra": f"{ra:.8f}",
        "dec": f"{dec:.8f}",
        "filters": filters,
        "type": "stack",
        "sep": ",",
    })
    return f"{PS1_FILENAMES_ENDPOINT}?{query}"


def parse_panstarrs_filename_table(text):
    rows = []
    for row in csv.DictReader(io.StringIO(str(text or ""))):
        normalized = {str(key).strip(): str(value or "").strip() for key, value in row.items() if key is not None}
        if normalized.get("filename") and normalized.get("filter"):
            rows.append(normalized)
    return rows


def select_panstarrs_color_files(rows):
    by_filter = {}
    for row in rows:
        filter_name = str(row.get("filter", "")).strip().lower()
        filename = str(row.get("filename", "")).strip()
        if filter_name in "grizy" and filename and filter_name not in by_filter:
            by_filter[filter_name] = filename
    if len(by_filter) < 2:
        return None
    available = [token for token in "grizy" if token in by_filter]
    blue_filter = available[0]
    red_filter = available[-1]
    green_filter = min(available, key=lambda token: abs("grizy".index(token) - 2))
    return {
        "red": by_filter[red_filter],
        "green": by_filter[green_filter],
        "blue": by_filter[blue_filter],
        "filters": {"red": red_filter, "green": green_filter, "blue": blue_filter},
    }


def panstarrs_color_cutout_url(ra, dec, size_degrees, color_files, max_pixels=2400):
    size_pixels = int(round(float(size_degrees) * 3600.0 / PS1_PIXEL_SCALE_ARCSEC))
    size_pixels = min(int(max_pixels), max(240, size_pixels))
    query = urllib.parse.urlencode({
        "ra": f"{float(ra) % 360.0:.8f}",
        "dec": f"{float(dec):.8f}",
        "size": str(size_pixels),
        "format": "jpg",
        "red": color_files["red"],
        "green": color_files["green"],
        "blue": color_files["blue"],
    })
    return f"{PS1_FITSCUT_ENDPOINT}?{query}"


def download_panstarrs_context(ra, dec, size_degrees, destination, timeout=120):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    filenames_url = panstarrs_filenames_url(ra, dec)
    request = urllib.request.Request(filenames_url, headers={"User-Agent": "Hubble-Workbench/2 Pan-STARRS-context"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        table_text = response.read().decode("utf-8", "replace")
    color_files = select_panstarrs_color_files(parse_panstarrs_filename_table(table_text))
    if not color_files:
        raise RuntimeError("Pan-STARRS did not return enough stacked filters for a color reference image at this position.")
    image_url = panstarrs_color_cutout_url(ra, dec, size_degrees, color_files)
    request = urllib.request.Request(image_url, headers={"User-Agent": "Hubble-Workbench/2 Pan-STARRS-context"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        content_type = str(response.headers.get("Content-Type", ""))
    if not data.startswith(b"\xff\xd8"):
        raise RuntimeError(f"Pan-STARRS did not return a JPEG image (content type: {content_type or 'unknown'}).")
    destination.write_bytes(data)
    metadata = {
        "source": "Pan-STARRS1 via MAST/STScI",
        "service_url": image_url,
        "filenames_service_url": filenames_url,
        "ra_degrees": float(ra) % 360.0,
        "dec_degrees": float(dec),
        "field_size_degrees": float(size_degrees),
        "filters": color_files["filters"],
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "image_path": str(destination),
        "usage_note": "Optical color-reference image; not yet WCS-registered as a science layer.",
    }
    metadata_path = destination.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata
