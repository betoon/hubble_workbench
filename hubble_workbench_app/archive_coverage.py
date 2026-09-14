"""Spherical footprints for previews and WCS-aligned shared-coverage products."""
import json
import re
from pathlib import Path

import numpy as np


def footprint_polygons(region):
    """Parse STC-S polygon lists without combining disconnected footprints."""
    polygons = []
    for part in re.split(r"\bPOLYGON\b", str(region), flags=re.I)[1:]:
        # A following shape starts a different STC-S region.
        part = re.split(r"\b(?:CIRCLE|BOX|UNION|INTERSECTION|NOT)\b", part, flags=re.I)[0]
        values = [float(x) for x in re.findall(r"(?<![\w.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?(?![\w.])", part)]
        if len(values) >= 6 and len(values) % 2 == 0:
            poly = np.array(values).reshape(-1,2)
            if np.isfinite(poly).all() and (np.abs(poly[:,1]) <= 90).all():
                polygons.append(poly.tolist())
    return polygons


def fits_footprint(path):
    from .fits_io import first_image_hdu, _celestial_wcs
    data, header = first_image_hdu(path)
    wcs = _celestial_wcs(header)
    h, w = data.shape
    # Sample each edge to reveal projection curvature, not only four corners.
    t = np.linspace(0,1,17)
    x = np.concatenate((t*w-.5, np.full(17,w-.5), (1-t)*w-.5, np.full(17,-.5)))
    y = np.concatenate((np.full(17,-.5),t*h-.5,np.full(17,h-.5),(1-t)*h-.5))
    ra, dec = wcs.pixel_to_world_values(x,y)
    return np.column_stack((ra,dec)).tolist()


def display_footprints(records):
    """Return polygons and labels; requested regions are never labeled as actual coverage."""
    result = []
    for record in records:
        polygons = record.get("footprints") or footprint_polygons(record.get("region", ""))
        kind = "FITS footprint" if record.get("footprints") else record.get("footprint_kind", "unknown")
        if not polygons and record.get("field_deg"):
            from astropy.coordinates import SkyCoord, SkyOffsetFrame
            from astropy import units as u
            center = SkyCoord(record["ra"], record["dec"], unit=u.deg)
            half = record["field_deg"]/2
            corners = SkyCoord(lon=[-half,half,half,-half]*u.deg, lat=[-half,-half,half,half]*u.deg,
                               frame=SkyOffsetFrame(origin=center)).icrs
            polygons = [np.column_stack((corners.ra.deg,corners.dec.deg)).tolist()]
            kind = "requested field"
        result.append((record, polygons, kind))
    return result


def project_polygons(polygons):
    """Project sky vertices to a local tangent-like display, handling RA wrap."""
    flat = np.concatenate([np.asarray(p) for p in polygons])
    angles = np.deg2rad(flat[:,0])
    ra0 = np.rad2deg(np.arctan2(np.sin(angles).mean(), np.cos(angles).mean()))
    dec0 = float(np.median(flat[:,1]))
    return [np.column_stack((((np.array(p)[:,0]-ra0+180)%360-180)*np.cos(np.deg2rad(dec0)),
                             np.array(p)[:,1]-dec0)) for p in polygons]


def align_shared(paths, output_dir, shared=True, cancel=None):
    from astropy.io import fits
    from .fits_io import wcs_align_fits_channels
    from .archive_catalog import check_cancel
    check_cancel(cancel)
    arrays, headers, metadata = wcs_align_fits_channels(paths, max_output_pixels=4_000_000)
    check_cancel(cancel)
    mask = np.logical_and.reduce([np.isfinite(a) for a in arrays])
    if shared and not mask.any():
        raise ValueError("These images have no shared sky coverage. Select a different set.")
    if shared:
        yy, xx = np.where(mask)
        x0,x1,y0,y1 = int(xx.min()),int(xx.max()+1),int(yy.min()),int(yy.max()+1)
        arrays = [np.where(mask,a,np.nan)[y0:y1,x0:x1].astype(np.float32) for a in arrays]
        for header in headers:
            header["CRPIX1"] -= x0
            header["CRPIX2"] -= y0
        metadata["crop_pixels"] = [x0,y0,x1,y1]
        metadata["mode"] = "celestial WCS shared coverage crop"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = []
    for index,(data,header) in enumerate(zip(arrays,headers)):
        check_cancel(cancel)
        path = out/f"aligned_{index+1}.fits"
        # Original headers may contain structural cards for the former image.
        clean = fits.Header()
        for key,value in header.items():
            if key not in ("SIMPLE","BITPIX","NAXIS","NAXIS1","NAXIS2","EXTEND","XTENSION","PCOUNT","GCOUNT","CHECKSUM","DATASUM"):
                try:
                    clean[key] = value
                except (ValueError,TypeError):
                    pass
        fits.PrimaryHDU(data,header=clean).writeto(path, overwrite=True, checksum=True)
        result.append(str(path))
    metadata["output_shape"] = list(arrays[0].shape)
    (out/"alignment.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    return result, metadata
