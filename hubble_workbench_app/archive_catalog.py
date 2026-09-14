"""Public image archive adapters. Queries never download science files."""
import csv
import io
import math
import re
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SOURCES = {
    "Pan-STARRS": "Optical g/r/i/z/y cutouts; sky north of -30 degrees.",
    "DSS": "Optical reference cutouts from digitized photographic surveys.",
    "WISE": "Infrared survey cutouts in four wavelength bands.",
    "Spitzer": "IRSA IRAC mosaics or calibrated exposures; files may exceed the requested field. Up to 20 exposures per band.",
    "GALEX": "Far- and near-ultraviolet reference cutouts; two bands, not a natural RGB set.",
    "Chandra": "Curated OpenFITS targets, searched by name; X-ray energy bands, not full archive coverage.",
}
SKY_SURVEYS = {
    "DSS": [("DSS2 Blue", "blue", 0.44), ("DSS2 Red", "green", 0.65), ("DSS2 IR", "red", 0.85)],
    "WISE": [("WISE 3.4", "blue", 3.4), ("WISE 4.6", "green", 4.6), ("WISE 12", "red", 12.0), ("WISE 22", "", 22.0)],
    "GALEX": [("GALEX Far UV", "blue", 0.153), ("GALEX Near UV", "red", 0.231)],
}


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("Stopped. Completed downloads remain in the cache.")


def network_session():
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=1, status=1, backoff_factor=0.5,
                  status_forcelist=(429, 502, 503, 504), allowed_methods=frozenset(("GET", "HEAD")))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def resolve_target(target):
    from astropy.coordinates import SkyCoord
    from astropy import units as u
    text = target.strip()
    if not text:
        raise ValueError("Enter a target name or RA, Dec in degrees.")
    try:
        ra, dec = [float(value) for value in text.replace(",", " ").split()]
        return SkyCoord(ra, dec, unit=u.deg)
    except ValueError:
        pass
    # Astropy's resolver has its own timeout; scope it to this call.
    from astropy.utils.data import conf
    with conf.set_temp("remote_timeout", 30):
        return SkyCoord.from_name(text)


def image_record(source, target, band, url, *, channel="", wavelength=None, size=None,
                 region="", footprint_kind="unknown", key=None, **extra):
    return dict(source=source, target=target, band=band, url=url, channel=channel,
                wavelength=wavelength, size=size, region=region, footprint_kind=footprint_kind,
                key=key or url, **extra)


class FitsLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.parts = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href", "")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            if urlparse(self.href).path.lower().endswith((".fits", ".fits.gz")):
                self.links.append((self.href, " ".join(self.parts).strip()))
            self.href = None


def chandra_records(html, target):
    base = "https://www.chandra.harvard.edu/photo/openFITS/xray_data.html"
    aliases = {"M42": "Orion", "M1": "Crab", "NGC1952": "Crab", "CASSIOPEIAA": "Cas A",
               "NGC5128": "Cen A", "CENT A": "Cen A", "SAGITTARIUSA*": "SGRA"}
    normalize = lambda text: re.sub(r"[^a-z0-9]", "", text.lower())
    requested = aliases.get(target.upper().replace(" ", ""), target)
    parser = FitsLinks()
    parser.feed(html)
    records = []
    available = set()
    for href, label in parser.links:
        name = re.split(r"\s+(?=\d+(?:\.\d+)?\s*[-–])|\s+[Bb]road", label)[0]
        name = re.sub(r"\s+[Ff]its.*", "", name).strip()
        available.add(name)
        if normalize(name) != normalize(requested):
            continue
        energy = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*keV", label, re.I)
        center = (float(energy[1]) + float(energy[2])) / 2 if energy else None
        records.append(image_record("Chandra", name, label, urljoin(base, href),
                                    wavelength=0.00123984 / center if center else None,
                                    credit="See Chandra OpenFITS source page for observation credits.", provenance=base))
    if not records:
        raise ValueError("No curated Chandra match. Available names include: " + ", ".join(sorted(available)))
    colored = sorted([r for r in records if r["wavelength"]], key=lambda r: r["wavelength"], reverse=True)
    if len(colored) >= 3:
        for channel, record in zip(("red", "green", "blue"), (colored[0], colored[len(colored)//2], colored[-1])):
            record["channel"] = channel
    return records


def search_archive(source, target, field_arcmin=5, pixels=512, cancel=None, progress=lambda text: None):
    if source not in SOURCES:
        raise ValueError("Choose an image archive.")
    if not math.isfinite(field_arcmin) or not 0.1 <= field_arcmin <= 60:
        raise ValueError("Field width must be between 0.1 and 60 arcminutes.")
    if not 64 <= pixels <= 2048:
        raise ValueError("Preview pixels must be between 64 and 2048.")
    check_cancel(cancel)
    if source == "Chandra":
        with network_session() as session:
            response = session.get("https://www.chandra.harvard.edu/photo/openFITS/xray_data.html", timeout=(15, 45))
            response.raise_for_status()
            check_cancel(cancel)
            return chandra_records(response.text, target)
    progress("Resolving target coordinates...")
    coord = resolve_target(target)
    ra, dec = float(coord.ra.deg), float(coord.dec.deg)
    check_cancel(cancel)
    progress(f"Searching {source}...")
    if source == "Pan-STARRS":
        if dec < -30:
            raise ValueError("Pan-STARRS does not cover this target (south of -30 degrees). Try DSS.")
        with network_session() as session:
            response = session.get("https://ps1images.stsci.edu/cgi-bin/ps1filenames.py",
                                   params=dict(ra=ra, dec=dec, filters="grizy", type="stack"), timeout=(15, 45))
            response.raise_for_status()
        from astropy.table import Table
        table = Table.read(response.text, format="ascii")
        result = []
        # PS1 pixels are 0.25 arcsec; cap cutouts at the archive limit.
        size = min(6000, max(24, round(field_arcmin * 60 / 0.25)))
        for row in table:
            band = str(row["filter"])
            params = dict(ra=ra, dec=dec, size=size, format="fits", red=str(row["filename"]))
            url = "https://ps1images.stsci.edu/cgi-bin/fitscut.cgi?" + urlencode(params)
            result.append(image_record(source, target, band, url, channel={"g":"blue", "r":"green", "i":"red"}.get(band,""),
                                       wavelength={"g":0.481,"r":0.617,"i":0.752,"z":0.866,"y":0.962}.get(band),
                                       size=size*size*4+28800, size_estimated=True,
                                       footprint_kind="requested field", ra=ra, dec=dec, field_deg=size*0.25/3600))
        check_cancel(cancel)
        return result
    if source in SKY_SURVEYS:
        from astroquery.skyview import SkyViewClass
        from astropy import units as u
        client = SkyViewClass()
        # SkyView's requests use a session; supply an inactivity timeout.
        from .mast_network import MastTimeoutAdapter
        client._session.mount("https://", MastTimeoutAdapter())
        client.URL = "https://skyview.gsfc.nasa.gov/current/cgi/basicform.pl"
        result = []
        for survey, channel, wavelength in SKY_SURVEYS[source]:
            check_cancel(cancel)
            progress(f"Preparing {source}: {survey} cutout...")
            urls = client.get_image_list(position=coord, survey=[survey], pixels=str(pixels),
                                         width=field_arcmin/60*u.deg, height=field_arcmin/60*u.deg)
            for url in urls:
                url = url.replace("http://skyview.gsfc.nasa.gov/", "https://skyview.gsfc.nasa.gov/")
                result.append(image_record(source, target, survey, url, channel=channel, wavelength=wavelength,
                                           key=f"{source}/{survey}/{ra:.8f}/{dec:.8f}/{field_arcmin}/{pixels}",
                                           size=pixels*pixels*4+28800, size_estimated=True,
                                           footprint_kind="requested field", ra=ra, dec=dec, field_deg=field_arcmin/60))
        return result
    # IRSA SIA2 returns calibrated Spitzer IRAC science mosaics and their footprint polygons.
    with network_session() as session:
        response = session.get("https://irsa.ipac.caltech.edu/SIA", params={
            "COLLECTION":"spitzer_sha", "POS":f"CIRCLE {ra} {dec} {field_arcmin/120}",
            "INSTRUMENT":"IRAC", "CALIB":3, "DPTYPE":"image", "MAXREC":200, "RESPONSEFORMAT":"CSV"}, timeout=(15,60))
        response.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(response.text)))
    if not rows:
        # Some SHA fields expose only level-2 frames. Query each band so a
        # large number of recent two-band exposures cannot hide older channels.
        with network_session() as session:
            for band in (3.6e-6, 4.5e-6, 5.8e-6, 8.0e-6):
                check_cancel(cancel)
                progress(f"Searching calibrated Spitzer {band*1e6:.1f} micron exposures...")
                response = session.get("https://irsa.ipac.caltech.edu/SIA", params={
                    "COLLECTION":"spitzer_sha", "POS":f"CIRCLE {ra} {dec} {field_arcmin/120}",
                    "INSTRUMENT":"IRAC", "CALIB":2, "BAND":band,
                    "DPTYPE":"image", "MAXREC":20, "RESPONSEFORMAT":"CSV"}, timeout=(15,60))
                response.raise_for_status()
                rows.extend(csv.DictReader(io.StringIO(response.text)))
    records = []
    for row in rows:
        url = row.get("access_url", "")
        if not url or "fits" not in row.get("access_format", "").lower():
            continue
        # SHA science mosaics end in maic; exclude uncertainties/coverage products.
        if not any(suffix in url.lower() for suffix in ("_maic.fits", "_cbcd.fits", "_bcd.fits")):
            continue
        try:
            wavelength = (float(row["em_min"]) + float(row["em_max"])) * 5e5
        except (KeyError, ValueError):
            wavelength = None
        try:
            size = int(float(row.get("access_estsize", "0"))) * 1024 or None
        except ValueError:
            size = None
        band = f"{wavelength:.2f} microns" if wavelength else row.get("obs_id", "IRAC")
        records.append(image_record(source, target, band, url, wavelength=wavelength, size=size,
                                    region=row.get("s_region", ""), footprint_kind="archive polygon" if row.get("s_region") else "unknown",
                                    observation=row.get("obs_id", ""), instrument="IRAC",
                                    product_type="mosaic" if "maic" in url else "calibrated exposure",
                                    provenance="https://irsa.ipac.caltech.edu/ibe/sia.html"))
    check_cancel(cancel)
    return records
