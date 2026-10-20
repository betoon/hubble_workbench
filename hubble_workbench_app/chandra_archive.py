"""Public Chandra observation-image search through the replacement CDA SIA API."""
import io
import math
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

ENDPOINT = 'https://cda.cfa.harvard.edu/cxcsiap/queryImages'
REFERENCE = 'https://cxcfps.cfa.harvard.edu/cda/footprint/cdaview.html'


def parse_chandra_images(content, target):
    from astropy.io.votable import parse_single_table
    from .archive_catalog import image_record
    from .archive_downloads import validate_archive_url
    root = ET.fromstring(content)
    for info in root.iter():
        if info.tag.rsplit('}', 1)[-1] == 'INFO' and info.get('name', '').upper() == 'QUERY_STATUS':
            status = info.get('value', '').upper()
            if status in ('ERROR', 'OVERFLOW'):
                raise ValueError('Chandra search ' + status.lower() + ': ' + (info.text or 'Narrow the search field and retry.'))
    table = parse_single_table(io.BytesIO(content)).to_table()
    required = {'accref', 'imgfmt', 'obsid', 'instrument'}
    if not required.issubset(table.colnames):
        raise ValueError('The Chandra service returned an unrecognized image table.')
    def text(row, key):
        value = row[key] if key in table.colnames else ''
        if getattr(value, 'mask', False):
            return ''
        return value.decode('utf-8') if isinstance(value, bytes) else str(value)
    def number(row, key):
        try:
            value = float(text(row, key))
            return value if math.isfinite(value) and value != -9999 else None
        except (ValueError, TypeError):
            return None
    records, seen = [], set()
    for row in table:
        if 'fits' not in text(row, 'imgfmt').lower():
            continue
        url = text(row, 'accref').strip()
        if not url or url in seen:
            continue
        validate_archive_url(url)
        if not (urlparse(url).hostname or '').endswith('.harvard.edu'):
            continue
        lo, hi = number(row, 'bandlo'), number(row, 'bandhi')
        band = f'{lo:g}-{hi:g} keV' if lo is not None and hi is not None else 'Broad X-ray'
        center = (lo+hi)/2 if lo is not None and hi is not None and hi >= lo > 0 else None
        obsid = text(row, 'obsid')
        size = number(row, 'filesize')
        exposure = number(row, 'exptime')
        record = image_record('Chandra', target, band, url,
            wavelength=.00123984/center if center else None,
            size=int(size) if size and size > 0 else None,
            instrument=text(row, 'instrument'), observation=obsid,
            observation_target=text(row, 'name'), epoch_mjd=number(row, 'date_obs'),
            exposure_seconds=exposure*1000 if exposure is not None else None,
            product_type='archive image', archive='Chandra Data Archive',
            ra=number(row, 'ra'), dec=number(row, 'dec'),
            footprint_kind='unknown', provenance=ENDPOINT,
            credit='NASA/CXC; retain the observation identifier and archive acknowledgments.',
            display_label=f'{band} | Obs {obsid} | ' + ('full field' if '_full_' in url else 'central field' if '_cntr_' in url else 'image'))
        records.append(record)
        seen.add(url)
    return records


def search_chandra_archive(target, ra, dec, field_arcmin, cancel=None, progress=lambda text: None):
    from .archive_catalog import check_cancel, network_session
    check_cancel(cancel)
    progress('Searching public Chandra observation images...')
    with network_session() as session:
        response = session.get(ENDPOINT, params={'POS': f'{ra},{dec}', 'SIZE': field_arcmin/60,
                                                 'FORMAT': 'image/fits'}, timeout=(15, 60))
        response.raise_for_status()
        check_cancel(cancel)
        records = parse_chandra_images(response.content, target)
    progress(f'Found {len(records)} Chandra FITS images. Full and central fields may both be listed.')
    return records
