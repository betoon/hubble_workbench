"""WCS-registered display overlays using only local FITS image pixels."""
from pathlib import Path
import numpy as np
from PIL import Image
from .fits_io import first_image_hdu, _celestial_wcs, _reproject_bilinear
from .image_processing import normalize_float_channel
from .overlay_controls import layer_settings, ordered_overlays

MAX_OVERLAYS = 8
PALETTE = ('#62b6ff', '#f4bf60', '#76dcac', '#f28fce', '#c0abff')

class SampledWCS:
    def __init__(self, wcs, step):
        self.wcs, self.step = wcs, step
    def world_to_pixel_values(self, ra, dec):
        x, y = self.wcs.world_to_pixel_values(ra, dec)
        return x/self.step, y/self.step

class CanvasSky:
    def __init__(self, geometry, raster_shape):
        self.geometry, self.raster_shape = geometry, raster_shape
    def pixel_to_world_values(self, xx, yy):
        g = self.geometry
        h, w = self.raster_shape
        screen_x, screen_y = (xx+.5)*g['width']/w, (yy+.5)*g['height']/h
        px = (g['width']/2-screen_x)/g['scale'] + g['center'][0]
        py = ((g['height']+60)/2-screen_y)/g['scale'] + g['center'][1]
        return (g['ra0'] + px/g['cosdec']) % 360, g['dec0'] + py


def load_overlay(record):
    path = Path(record.get('local_path', ''))
    if not path.is_file():
        raise ValueError('Download this image in Image Wizard first.')
    data, header = first_image_hdu(path)
    wcs = _celestial_wcs(header)
    height, width = data.shape
    footprint = wcs.calc_footprint(axes=(width, height))
    if footprint is None or not np.isfinite(footprint).all():
        raise ValueError('No valid celestial WCS footprint.')
    step = max(1, int(np.ceil(max(data.shape)/1200)))
    sampled = np.asarray(data[::step, ::step], dtype=np.float32)
    valid = np.isfinite(sampled)
    stretched = normalize_float_channel(sampled)
    stretched[~valid] = np.nan
    updated = dict(record, footprints=[footprint.tolist()])
    return {'record': updated, 'pixels': stretched, 'wcs': SampledWCS(wcs, step)}


def render_overlays(overlays, geometry, mode, opacity, source_names, settings=None):
    if mode == 'Off' or not overlays or opacity <= 0:
        return None
    if mode not in ('Grayscale', 'Source colors'):
        raise ValueError('Unknown overlay display mode.')
    opacity = float(np.clip(opacity, 0, 1))
    h, w = max(1, int(geometry['height'])), max(1, int(geometry['width']))
    factor = max(w/700, h/500, 1)
    shape = (max(1, round(h/factor)), max(1, round(w/factor)))
    sky = CanvasSky(geometry, shape)
    rgb = np.zeros((*shape, 3), dtype=np.float32)
    alpha = np.zeros(shape, dtype=np.float32)
    for overlay in overlays:
        options = layer_settings(settings or {}, overlay['record']['key'])
        if not options['visible'] or options['opacity'] <= 0:
            continue
        values = _reproject_bilinear(overlay['pixels'], overlay['wcs'], sky, shape)
        valid = np.isfinite(values)
        color = np.ones(3, dtype=np.float32)
        if mode == 'Source colors':
            code = PALETTE[source_names.index(overlay['record'].get('source', 'Unknown')) % len(PALETTE)]
            color = np.array([int(code[i:i+2], 16)/255 for i in (1,3,5)])
        a = valid.astype(np.float32)*opacity*options["opacity"]
        rgb = np.nan_to_num(values)[...,None]*color*a[...,None] + rgb*(1-a[...,None])
        alpha = a + alpha*(1-a)
    # PIL expects straight, not premultiplied, alpha.
    straight = np.divide(rgb, alpha[...,None], out=np.zeros_like(rgb), where=alpha[...,None]>0)
    rgba = np.concatenate((straight, alpha[...,None]), axis=2)
    image = Image.fromarray(np.uint8(np.clip(rgba, 0, 1)*255), 'RGBA')
    return image.resize((w,h), Image.Resampling.NEAREST)


def start_overlay_load(app, records=None, switch_tab=True):
    from .archive_catalog import check_cancel
    if getattr(app, 'wizard_busy', False):
        app.wizard_status.set('Finish or stop the current Wizard operation before loading overlays.')
        return
    records = list(app.wizard_selected() if records is None else records)
    if not records:
        app.wizard_status.set('Select downloaded images in Image Wizard, then choose Show in Explorer.')
        return
    if len(records) > MAX_OVERLAYS:
        app.wizard_status.set(f'Select at most {MAX_OVERLAYS} images for an overlay comparison.')
        return
    app.wizard_overlay_generation = getattr(app, 'wizard_overlay_generation', 0)+1
    generation = app.wizard_overlay_generation
    app.wizard_overlay_keys = [r['key'] for r in records]
    def work(cancel):
        loaded, errors = [], []
        for record in records:
            check_cancel(cancel)
            try:
                loaded.append(load_overlay(dict(record)))
            except Exception as exc:
                errors.append(f"{record.get('source')} / {record.get('band')}: {exc}")
        check_cancel(cancel)
        return loaded, errors
    def finish(result):
        if generation != getattr(app, 'wizard_overlay_generation', None):
            return
        loaded, errors = result
        current = {r['key']: r for r in app.wizard_records}
        loaded = [item for item in loaded if item['record']['key'] in current
                  and item['record'].get('local_path') == current[item['record']['key']].get('local_path')]
        app.wizard_overlay_cache = ordered_overlays(loaded, app.wizard_overlay_keys)
        app.wizard_overlay_render_key = None
        for item in loaded:
            current[item['record']['key']]['footprints'] = item['record']['footprints']
        if switch_tab and loaded:
            app.mosaic_layer_var.set('Image Wizard: All')
            if app.wizard_overlay_mode.get() == 'Off':
                app.wizard_overlay_mode.set('Source colors')
            app.notebook.select(app.observatory_tab)
        app.observatory_draw_current_mosaic()
        if hasattr(app, "refresh_overlay_controls"):
            app.refresh_overlay_controls()
        message = f'Loaded {len(loaded)} local image overlays.'
        if errors:
            message += ' Skipped: ' + '; '.join(errors)
        app.wizard_status.set(message)
        app.mosaic_status_var.set(message)
    app.wizard_start(work, finish)
