"""Explorer views of saved Wizard coverage; no network access is needed."""
import numpy as np
from .archive_coverage import display_footprints, project_polygons
from .image_overlays import render_overlays, start_overlay_load
from .overlay_controls import ordered_overlays, layer_settings

WIZARD_LAYERS = ["Image Wizard: All"] + ["Image Wizard: " + name for name in
    ("Hubble", "James Webb", "Pan-STARRS", "DSS", "WISE", "Spitzer", "GALEX", "Chandra")]
MAST_LAYERS = ["All active sources", "Hubble / HST", "JWST"]

def layer_records(records, layer):
    name = layer.removeprefix("Image Wizard: ")
    aliases = {"Hubble": "HST", "James Webb": "JWST"}
    return [r for r in records if name == "All" or str(r.get("source", "")).casefold()
            in {name.casefold(), aliases.get(name, name).casefold()}]


def draw_wizard_layer(app):
    canvas = app.mosaic_canvas
    app.wizard_mosaic_polygons = []
    records = layer_records(getattr(app, "wizard_records", []), app.mosaic_layer_var.get())
    entries = []
    unknown = 0
    for record in records:
        valid = []
        try:
            for _, polygons, kind in display_footprints([record]):
                for polygon in polygons:
                    points = np.asarray(polygon, dtype=float)
                    if points.ndim == 2 and points.shape[1] == 2 and len(points) >= 3 and np.isfinite(points).all():
                        valid.append((record, polygon, kind))
        except (ValueError, TypeError, KeyError):
            pass
        entries.extend(valid)
        unknown += not bool(valid)
    if entries:
        projected = project_polygons([entry[1] for entry in entries])
        flat = np.concatenate(projected)
        low, high = flat.min(axis=0), flat.max(axis=0)
        width, height = max(400, canvas.winfo_width()), max(300, canvas.winfo_height())
        scale = min((width-60)/max(high[0]-low[0], 1e-8), (height-90)/max(high[1]-low[1], 1e-8))
        colors = ("#62b6ff", "#f4bf60", "#76dcac", "#f28fce", "#c0abff")
        sources = sorted({entry[0].get("source", "Unknown") for entry in entries})
        center = (low + high) / 2
        mode_var = getattr(app, 'wizard_overlay_mode', None)
        mode = mode_var.get() if mode_var else 'Off'
        if mode != 'Off':
            from PIL import ImageTk
            raw = np.concatenate([np.asarray(entry[1]) for entry in entries])
            angles = np.deg2rad(raw[:,0])
            ra0 = float(np.rad2deg(np.arctan2(np.sin(angles).mean(), np.cos(angles).mean())))
            dec0 = float(np.median(raw[:,1]))
            geometry = dict(width=width, height=height, center=center, scale=scale,
                            ra0=ra0, dec0=dec0, cosdec=max(1e-8, float(np.cos(np.deg2rad(dec0)))))
            keys = {r.get('key') for r in records}
            overlays = [item for item in getattr(app, 'wizard_overlay_cache', []) if item['record'].get('key') in keys]
            overlays = ordered_overlays(overlays, getattr(app, "wizard_overlay_keys", []))
            settings = getattr(app, "wizard_overlay_settings", {})
            opacity = float(app.wizard_overlay_opacity.get())
            render_key = (width, height, tuple(center), scale, ra0, dec0, mode, opacity,
                          tuple((id(item), tuple(layer_settings(settings, item["record"]["key"]).values())) for item in overlays), tuple(sources))
            if render_key != getattr(app, 'wizard_overlay_render_key', None):
                rendered = render_overlays(overlays, geometry, mode, opacity, sources, settings)
                app.wizard_overlay_photo = ImageTk.PhotoImage(rendered) if rendered is not None else None
                app.wizard_overlay_render_key = render_key
            if getattr(app, 'wizard_overlay_photo', None) is not None:
                canvas.create_image(0, 0, anchor='nw', image=app.wizard_overlay_photo)

        label_positions = []
        for (record, _, kind), points in zip(entries, projected):
            xy = np.column_stack((width/2-(points[:,0]-center[0])*scale,
                                  (height+60)/2-(points[:,1]-center[1])*scale))
            canvas.create_polygon(*xy.flatten(), fill="", outline=colors[sources.index(record.get("source", "Unknown")) % len(colors)],
                                  width=2, dash=(4,3) if kind == "requested field" else ())
            app.wizard_mosaic_polygons.append({"record": record, "points": xy.tolist()})
            label_x, label_y = float(xy[:,0].min())+4, float(xy[:,1].min())+4
            while any(abs(label_x-x) < 180 and abs(label_y-y) < 14 for x,y in label_positions):
                label_y += 14
            label_positions.append((label_x,label_y))
            canvas.create_text(label_x, label_y,
                               anchor="nw", fill=colors[sources.index(record.get("source", "Unknown")) % len(colors)],
                               text="{} / {}".format(record.get("source", "Unknown"), record.get("band", "")))
    canvas.create_text(12, 12, anchor="nw", fill="white", text=
        "Image Wizard coverage — north up, east left\nDashed: requested field; solid: archive/FITS boundary. Click inside to open in Wizard.")
    if not entries:
        canvas.create_text(12, 75, anchor="nw", fill="white", text="No known coverage in this layer. Find images in Image Wizard first.")
    app.mosaic_status_var.set(f"{len(records)} Wizard records; {unknown} without drawable coverage. "
                              "MAST filters do not apply. Image overlays are independently stretched display comparisons; boundaries do not guarantee valid-pixel overlap.")


def select_wizard_footprint(app, event):
    for item in reversed(getattr(app, "wizard_mosaic_polygons", [])):
        if app.observatory_point_in_polygon(event.x, event.y, item["points"]):
            record = item["record"]
            for index, candidate in enumerate(getattr(app, "wizard_records", [])):
                if candidate is record or candidate == record:
                    app.wizard_tree.selection_set(str(index))
                    app.wizard_tree.see(str(index))
                    app.wizard_review()
                    app.notebook.select(app.wizard_tab)
                    return record
    return None


def explorer_state(app):
    if not hasattr(app, 'mosaic_layer_var'):
        return {}
    state = {'layer': app.mosaic_layer_var.get()}
    if hasattr(app, 'wizard_overlay_mode'):
        state.update(overlay_mode=app.wizard_overlay_mode.get(),
                     overlay_opacity=app.wizard_overlay_opacity.get(),
                     overlay_keys=getattr(app, 'wizard_overlay_keys', []),
                     overlay_settings=getattr(app, 'wizard_overlay_settings', {}))
    return state


def restore_explorer_state(app, state):
    if not hasattr(app, 'mosaic_layer_var'):
        return
    app.wizard_overlay_generation = getattr(app, 'wizard_overlay_generation', 0)+1
    app.wizard_overlay_cache = []
    app.wizard_overlay_render_key = None
    app.wizard_overlay_keys = state.get('overlay_keys', [])
    app.wizard_overlay_settings = {key: layer_settings(state.get('overlay_settings', {}), key) for key in app.wizard_overlay_keys}
    if hasattr(app, 'wizard_overlay_mode'):
        mode = state.get('overlay_mode', 'Off')
        app.wizard_overlay_mode.set(mode if mode in ('Off', 'Grayscale', 'Source colors') else 'Off')
        try:
            opacity = float(state.get('overlay_opacity', .65))
            if not np.isfinite(opacity):
                raise ValueError()
        except (TypeError, ValueError):
            opacity = .65
        app.wizard_overlay_opacity.set(min(1, max(0, opacity)))
    layer = state.get('layer', MAST_LAYERS[0])
    app.mosaic_layer_var.set(layer if layer in MAST_LAYERS + WIZARD_LAYERS else MAST_LAYERS[0])
    if hasattr(app, 'mosaic_canvas'):
        app.observatory_draw_current_mosaic()
    if hasattr(app, 'wizard_overlay_mode') and app.wizard_overlay_keys:
        by_key = {r.get('key'): r for r in getattr(app, 'wizard_records', [])}
        selected = [by_key[key] for key in app.wizard_overlay_keys if key in by_key]
        if selected:
            start_overlay_load(app, selected, switch_tab=False)
