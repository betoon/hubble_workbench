import threading
import json
from xml.sax.saxutils import escape
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import numpy as np
from PIL import Image, ImageOps

from .fits_io import FITS, _celestial_wcs, first_image_hdu, first_image_hdu_details
from .image_processing import downsample_array_for_preview, normalize_image, normalize_image_uint16
from .paths import DOWNLOAD_DIR, OUTPUT_DIR
from .settings import SETTINGS, save_settings


class PreviewWorkflowMixin:
    PREVIEW_METADATA_GROUPS = (
        ("File and Image", ("FILENAME", "EXTNAME", "NAXIS1", "NAXIS2", "BITPIX", "BUNIT")),
        ("Target and Observation", ("TARGNAME", "OBJECT", "TELESCOP", "INSTRUME", "DETECTOR", "FILTER", "FILTER1", "FILTER2", "EXPTIME", "DATE-OBS", "TIME-OBS", "PROPOSID", "PROGRAM")),
        ("World Coordinates", ("RADESYS", "RADECSYS", "EQUINOX", "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CDELT1", "CDELT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2")),
    )

    @staticmethod
    def discover_recent_fits_files(folder, limit=100):
        folder = Path(folder)
        if not folder.exists():
            return []
        files = [
            path for path in folder.rglob("*")
            if path.is_file() and path.name.lower().endswith((".fits", ".fits.gz", ".fit"))
        ]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files[:max(0, int(limit))]

    def refresh_recent_fits_files(self):
        paths = self.discover_recent_fits_files(DOWNLOAD_DIR)
        self.preview_recent_fits_paths = paths
        labels = [str(path.relative_to(DOWNLOAD_DIR)) for path in paths]
        self.preview_recent_fits_combo.configure(values=labels)
        current_path = self.convert_path_var.get().strip()
        if current_path:
            try:
                relative = str(Path(current_path).relative_to(DOWNLOAD_DIR))
                if relative in labels:
                    self.preview_recent_fits_var.set(relative)
            except (ValueError, OSError):
                pass
        if hasattr(self, "convert_status"):
            self.convert_status.set(
                f"Found {len(paths)} recent FITS file(s) under {DOWNLOAD_DIR}."
                if paths else f"No FITS files were found under {DOWNLOAD_DIR}."
            )
        return paths

    def select_recent_fits_file(self, _event=None):
        selected = self.preview_recent_fits_var.get()
        if not selected:
            return None
        path = DOWNLOAD_DIR / selected
        if not path.is_file():
            self.convert_status.set("The selected recent FITS file is no longer available. Refresh the list.")
            return None
        self.convert_path_var.set(str(path))
        self.convert_status.set(f"Selected recent FITS file: {path.name}")
        return path

    @staticmethod
    def preview_image_statistics(data, sample_limit=1_000_000):
        values = np.asarray(data).reshape(-1)
        if values.size > sample_limit:
            step = max(1, values.size // sample_limit)
            values = values[::step]
        finite = values[np.isfinite(values)]
        if not finite.size:
            return {"sampled": int(values.size), "finite": 0}
        low, median, high = np.percentile(finite, (1, 50, 99))
        return {
            "sampled": int(values.size),
            "finite": int(finite.size),
            "minimum": float(np.min(finite)),
            "maximum": float(np.max(finite)),
            "mean": float(np.mean(finite)),
            "median": float(median),
            "stddev": float(np.std(finite)),
            "percentile_1": float(low),
            "percentile_99": float(high),
        }

    @staticmethod
    def preview_histogram(data, bins=192, sample_limit=1_000_000, black_percent=0.5, white_percent=99.5):
        values = np.asarray(data).reshape(-1)
        if values.size > sample_limit:
            step = max(1, values.size // sample_limit)
            values = values[::step]
        finite = values[np.isfinite(values)]
        if not finite.size:
            return {}
        black, white = np.percentile(finite, (black_percent, white_percent))
        lower, upper = np.percentile(finite, (0.1, 99.9))
        if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
            lower, upper = float(np.min(finite)), float(np.max(finite))
        if upper <= lower:
            upper = lower + 1.0
        counts, edges = np.histogram(finite, bins=max(16, int(bins)), range=(lower, upper))
        return {
            "counts": counts.astype(int).tolist(),
            "edges": edges.astype(float).tolist(),
            "black": float(black),
            "white": float(white),
            "sampled": int(finite.size),
        }

    @staticmethod
    def preview_stretch_percentiles(black, white):
        try:
            black = float(black)
            white = float(white)
        except (TypeError, ValueError) as exc:
            raise ValueError("Black and white points must be numeric percentiles.") from exc
        if not 0 <= black < white <= 100:
            raise ValueError("Use percentiles from 0 to 100, with the black point below the white point.")
        if white - black < 0.01:
            raise ValueError("Black and white percentiles must be at least 0.01 apart.")
        return black, white

    @classmethod
    def preview_stretch_settings_payload(cls, stretch, black, white, crosshair=False, flip_vertical=False, bit_depth=8):
        black, white = cls.preview_stretch_percentiles(black, white)
        stretch = str(stretch or "").lower()
        if stretch not in {"asinh", "pow", "sqrt", "log", "linear"}:
            raise ValueError(f"Unsupported preview stretch: {stretch or 'empty'}")
        bit_depth = int(bit_depth)
        if bit_depth not in (8, 16):
            raise ValueError("FITS preview export depth must be 8 or 16 bits.")
        return {
            "fits_preview_stretch": stretch,
            "fits_preview_black_percent": black,
            "fits_preview_white_percent": white,
            "fits_preview_crosshair": bool(crosshair),
            "fits_preview_flip_vertical": bool(flip_vertical),
            "fits_preview_export_bit_depth": bit_depth,
        }

    @staticmethod
    def preview_pixel_scale_arcsec(header):
        try:
            cd11 = float(header.get("CD1_1", header.get("CDELT1", 0)) or 0)
            cd12 = float(header.get("CD1_2", 0) or 0)
            cd21 = float(header.get("CD2_1", 0) or 0)
            cd22 = float(header.get("CD2_2", header.get("CDELT2", 0)) or 0)
            x_scale = 3600.0 * (cd11 * cd11 + cd21 * cd21) ** 0.5
            y_scale = 3600.0 * (cd12 * cd12 + cd22 * cd22) ** 0.5
            if x_scale > 0 and y_scale > 0:
                return x_scale, y_scale
        except (TypeError, ValueError):
            pass
        return None

    @classmethod
    def preview_metadata_summary(cls, header, shape, statistics=None, path=""):
        height, width = shape
        lines = ["FITS SCIENCE SUMMARY", "=" * 42]
        if path:
            lines.extend((f"File: {Path(path).name}", f"Location: {Path(path).parent}"))
        lines.extend((f"Dimensions: {width:,} x {height:,} pixels", f"Total pixels: {width * height:,}"))
        for title, keys in cls.PREVIEW_METADATA_GROUPS:
            entries = [(key, header.get(key)) for key in keys if header.get(key) not in (None, "")]
            if not entries:
                continue
            lines.extend(("", title.upper(), "-" * len(title)))
            lines.extend(f"{key}: {value}" for key, value in entries)
        scale = cls.preview_pixel_scale_arcsec(header)
        if scale:
            lines.extend((
                f"Pixel scale: {scale[0]:.4f} x {scale[1]:.4f} arcsec/pixel",
                f"Approx. field of view: {width * scale[0] / 60:.2f} x {height * scale[1] / 60:.2f} arcmin",
            ))
        if statistics and statistics.get("finite"):
            lines.extend(("", "IMAGE STATISTICS", "----------------"))
            for label, key in (("Minimum", "minimum"), ("Maximum", "maximum"), ("Mean", "mean"), ("Median", "median"), ("Standard deviation", "stddev"), ("1st percentile", "percentile_1"), ("99th percentile", "percentile_99")):
                lines.append(f"{label}: {statistics[key]:.7g}")
            lines.append(f"Finite sample: {statistics['finite']:,} of {statistics['sampled']:,} values")
        return "\n".join(lines)

    @staticmethod
    def preview_header_text(header, query="", cards=None):
        query = str(query or "").strip().lower()
        rows = []
        source = cards or (
            {"keyword": key, "value": value, "type": type(value).__name__, "comment": ""}
            for key, value in header.items()
        )
        for card in source:
            key = card.get("keyword", "")
            value = card.get("value", "")
            value_type = card.get("type", "")
            comment = card.get("comment", "")
            line = f"{key:<10} = {str(value):<30}  [{value_type}]"
            if comment:
                line += f"  / {comment}"
            if not query or query in line.lower():
                rows.append(line)
        return "\n".join(rows) if rows else "No FITS header fields match the current search."

    @staticmethod
    def preview_hdu_inventory_text(inventory):
        if not inventory:
            return "No HDU information is available."
        lines = [
            "FITS HDU / EXTENSION INVENTORY",
            "=" * 72,
            f"{'HDU':<5} {'Name':<14} {'Type':<18} {'Dimensions':<20} {'BITPIX':<7} Cards",
            "-" * 72,
        ]
        for item in inventory:
            shape = " x ".join(str(value) for value in reversed(item.get("shape", ()))) or "No data"
            marker = "*" if item.get("selected") else " "
            lines.append(
                f"{marker}{item.get('index', 0):<4} "
                f"{str(item.get('name', ''))[:13]:<14} "
                f"{str(item.get('type', ''))[:17]:<18} "
                f"{shape[:19]:<20} "
                f"{str(item.get('bitpix', '')):<7} "
                f"{item.get('cards', 0)}"
            )
        lines.extend(("", "* HDU currently used for the image preview.", f"Total extensions: {len(inventory)}"))
        return "\n".join(lines)

    @staticmethod
    def preview_canvas_to_image_point(
        canvas_x,
        canvas_y,
        canvas_size,
        rendered_size,
        image_size,
    ):
        canvas_width, canvas_height = canvas_size
        rendered_width, rendered_height = rendered_size
        image_width, image_height = image_size
        left = (canvas_width - rendered_width) / 2.0
        top = (canvas_height - rendered_height) / 2.0
        if not (
            left <= canvas_x < left + rendered_width
            and top <= canvas_y < top + rendered_height
            and rendered_width > 0
            and rendered_height > 0
        ):
            return None
        image_x = min(image_width - 1, max(0, int((canvas_x - left) * image_width / rendered_width)))
        image_y = min(image_height - 1, max(0, int((canvas_y - top) * image_height / rendered_height)))
        return image_x, image_y

    @staticmethod
    def preview_display_to_source_point(point, image_size, flip_vertical=False):
        if point is None:
            return None
        x, y = point
        if flip_vertical:
            y = image_size[1] - 1 - y
        return x, y

    @staticmethod
    def preview_format_sky_position(ra, dec):
        if not (np.isfinite(ra) and np.isfinite(dec)):
            return ""
        ra_hours = (float(ra) % 360.0) / 15.0
        ra_h = int(ra_hours)
        ra_minutes = (ra_hours - ra_h) * 60.0
        ra_m = int(ra_minutes)
        ra_s = (ra_minutes - ra_m) * 60.0
        sign = "+" if dec >= 0 else "-"
        dec_abs = abs(float(dec))
        dec_d = int(dec_abs)
        dec_minutes = (dec_abs - dec_d) * 60.0
        dec_m = int(dec_minutes)
        dec_s = (dec_minutes - dec_m) * 60.0
        return (
            f"RA {ra:10.6f}° ({ra_h:02d}h {ra_m:02d}m {ra_s:05.2f}s)  |  "
            f"Dec {dec:+10.6f}° ({sign}{dec_d:02d}° {dec_m:02d}′ {dec_s:04.1f}″)"
        )

    def choose_convert_file(self):
        path = filedialog.askopenfilename(
            title="Choose FITS File",
            initialdir=str(DOWNLOAD_DIR),
            filetypes=[("FITS files", "*.fits *.fits.gz *.fit"), ("All files", "*.*")],
        )
        if path:
            self.convert_path_var.set(path)

    def preview_fits_async(self):
        if not self.require_astropy():
            return
        path = self.convert_path_var.get().strip()
        if not path:
            messagebox.showinfo("Preview FITS", "Choose a FITS file first.")
            return
        try:
            black_percent, white_percent = self.preview_stretch_percentiles(
                self.preview_black_percent_var.get(),
                self.preview_white_percent_var.get(),
            )
        except ValueError as exc:
            self.convert_status.set(f"Preview settings need attention: {exc}")
            return
        stretch = self.stretch_var.get()
        same_file = path == getattr(self, "preview_loaded_path", None)
        hdu_index = getattr(self, "preview_selected_hdu_index", None) if same_file else None
        plane_index = int(self.preview_plane_var.get()) if same_file and hasattr(self, "preview_plane_var") else 0
        self.convert_status.set("Reading FITS image...")

        def worker():
            try:
                data, header, cards, inventory = first_image_hdu_details(path, hdu_index, plane_index)
                statistics = self.preview_image_statistics(data)
                histogram = self.preview_histogram(
                    data,
                    black_percent=black_percent,
                    white_percent=white_percent,
                )
                normalized = normalize_image(
                    data,
                    low_percent=black_percent,
                    high_percent=white_percent,
                    stretch=stretch,
                )
                result = (normalized, header, statistics, histogram, cards, inventory, path, data, None)
            except Exception as exc:
                result = (None, {}, {}, {}, [], [], path, None, exc)
            self.after(0, lambda: self.finish_preview(result))

        threading.Thread(target=worker, daemon=True).start()

    def reset_preview_stretch(self):
        self.preview_black_percent_var.set("0.5")
        self.preview_white_percent_var.set("99.5")
        self.convert_status.set("Restored automatic black and white points. Select Apply Stretch to refresh the preview.")

    def save_preview_stretch_settings(self):
        try:
            payload = self.preview_stretch_settings_payload(
                self.stretch_var.get(),
                self.preview_black_percent_var.get(),
                self.preview_white_percent_var.get(),
                self.preview_crosshair_var.get(),
                self.preview_flip_vertical_var.get(),
                self.preview_export_bit_depth_var.get(),
            )
        except ValueError as exc:
            self.convert_status.set(f"Preview settings were not saved: {exc}")
            return False
        SETTINGS.update(payload)
        save_settings(SETTINGS)
        self.convert_status.set("Saved FITS preview stretch and display settings.")
        return True

    def apply_saved_preview_stretch_settings(self):
        try:
            payload = self.preview_stretch_settings_payload(
                SETTINGS.get("fits_preview_stretch", "asinh"),
                SETTINGS.get("fits_preview_black_percent", 0.5),
                SETTINGS.get("fits_preview_white_percent", 99.5),
                SETTINGS.get("fits_preview_crosshair", False),
                SETTINGS.get("fits_preview_flip_vertical", False),
                SETTINGS.get("fits_preview_export_bit_depth", 8),
            )
        except ValueError as exc:
            self.convert_status.set(f"Saved preview settings are invalid: {exc}")
            return False
        self.stretch_var.set(payload["fits_preview_stretch"])
        self.preview_black_percent_var.set(f"{payload['fits_preview_black_percent']:g}")
        self.preview_white_percent_var.set(f"{payload['fits_preview_white_percent']:g}")
        self.preview_crosshair_var.set(payload["fits_preview_crosshair"])
        self.preview_flip_vertical_var.set(payload["fits_preview_flip_vertical"])
        self.preview_export_bit_depth_var.set(str(payload["fits_preview_export_bit_depth"]))
        self.redraw_fits_preview()
        self.convert_status.set("Applied saved FITS preview settings. Select Apply Stretch to reload the image.")
        return True

    def finish_preview(self, result):
        if len(result) == 3:
            image, header, error = result
            statistics, histogram, cards, inventory, path = {}, {}, [], [], self.convert_path_var.get().strip()
        elif len(result) == 5:
            image, header, statistics, path, error = result
            histogram, cards, inventory = {}, [], []
        elif len(result) == 6:
            image, header, statistics, histogram, path, error = result
            cards, inventory = [], []
        elif len(result) == 8:
            image, header, statistics, histogram, cards, inventory, path, error = result
            source_data = None
        else:
            image, header, statistics, histogram, cards, inventory, path, source_data, error = result
        if error:
            self.convert_status.set(f"Preview failed: {error}")
            return
        self.preview_image = Image.fromarray(image, mode="L")
        self.preview_source_data = source_data
        self.preview_header = dict(header)
        self.preview_statistics = dict(statistics)
        self.preview_histogram_data = dict(histogram)
        self.preview_header_cards = list(cards)
        self.preview_hdu_inventory = list(inventory)
        self.preview_loaded_path = path
        selected = next((item for item in inventory if item.get("selected")), None)
        self.preview_selected_hdu_index = selected.get("index") if selected else None
        self.refresh_preview_hdu_controls()
        self.reset_preview_view(redraw=False)
        try:
            self.preview_wcs = _celestial_wcs(header)
        except Exception:
            self.preview_wcs = None
        self.redraw_fits_preview()
        self.draw_preview_histogram()
        summary = self.preview_metadata_summary(header, self.preview_image.size[::-1], statistics, path)
        self.preview_summary_text.delete("1.0", "end")
        self.preview_summary_text.insert("1.0", summary)
        self.refresh_preview_header_search()
        self.preview_hdu_text.delete("1.0", "end")
        self.preview_hdu_text.insert("1.0", self.preview_hdu_inventory_text(inventory))
        self.clear_preview_probe(update_status=False)
        self.convert_status.set(f"Preview loaded at {self.preview_image.width} x {self.preview_image.height}px. Display is scaled to fit the canvas.")

    @staticmethod
    def preview_image_hdu_choices(inventory):
        choices = []
        for item in inventory or ():
            shape = tuple(item.get("shape", ()) or ())
            if len(shape) < 2:
                continue
            dimensions = " x ".join(map(str, reversed(shape)))
            label = f"{item.get('index', 0)}: {item.get('name', 'PRIMARY')}  ({dimensions})"
            choices.append((label, int(item.get("index", 0)), max(1, int(np.prod(shape[:-2])))))
        return choices

    def refresh_preview_hdu_controls(self):
        if not hasattr(self, "preview_hdu_combo"):
            return
        choices = self.preview_image_hdu_choices(getattr(self, "preview_hdu_inventory", []))
        self.preview_hdu_choice_map = {label: (index, planes) for label, index, planes in choices}
        self.preview_hdu_combo.configure(values=list(self.preview_hdu_choice_map))
        selected_index = getattr(self, "preview_selected_hdu_index", None)
        selected_label = next(
            (label for label, (index, _planes) in self.preview_hdu_choice_map.items() if index == selected_index),
            "",
        )
        if not selected_label:
            return
        self.preview_hdu_var.set(selected_label)
        planes = self.preview_hdu_choice_map[selected_label][1]
        self.preview_plane_spin.configure(
            to=max(0, planes - 1),
            state="normal" if planes > 1 else "disabled",
        )
        if int(self.preview_plane_var.get()) >= planes:
            self.preview_plane_var.set(0)

    def select_preview_hdu(self, _event=None):
        selection = getattr(self, "preview_hdu_choice_map", {}).get(self.preview_hdu_var.get())
        if not selection:
            return
        self.preview_selected_hdu_index, planes = selection
        self.preview_plane_var.set(0)
        self.preview_plane_spin.configure(
            to=max(0, planes - 1),
            state="normal" if planes > 1 else "disabled",
        )
        self.preview_fits_async()

    def select_preview_plane(self):
        self.preview_fits_async()

    @staticmethod
    def preview_histogram_x(value, lower, upper, left, right):
        if upper <= lower:
            return float(left)
        fraction = min(1.0, max(0.0, (float(value) - lower) / (upper - lower)))
        return float(left) + fraction * (float(right) - float(left))

    def draw_preview_histogram(self, _event=None):
        if not hasattr(self, "preview_histogram_canvas"):
            return
        canvas = self.preview_histogram_canvas
        canvas.delete("all")
        histogram = getattr(self, "preview_histogram_data", {}) or {}
        counts = histogram.get("counts", [])
        edges = histogram.get("edges", [])
        if not counts or len(edges) != len(counts) + 1:
            canvas.create_text(10, 10, text="Histogram appears after a FITS preview is loaded.", anchor="nw", fill="#6b7280")
            return
        width = max(320, canvas.winfo_width())
        height = max(110, canvas.winfo_height())
        left, right, top, bottom = 48, width - 12, 12, height - 28
        canvas.create_rectangle(left, top, right, bottom, fill="#f8fafc", outline="#9ca3af")
        log_counts = np.log10(np.asarray(counts, dtype=float) + 1.0)
        peak = max(1.0, float(np.max(log_counts)))
        points = []
        for index, value in enumerate(log_counts):
            x = left + index * (right - left) / max(1, len(log_counts) - 1)
            y = bottom - float(value) * (bottom - top) / peak
            points.extend((x, y))
        if len(points) >= 4:
            polygon = [left, bottom, *points, right, bottom]
            canvas.create_polygon(polygon, fill="#cbd5e1", outline="#64748b")
        lower, upper = float(edges[0]), float(edges[-1])
        self.preview_histogram_plot = (left, right, lower, upper)
        for value, color, label in (
            (histogram.get("black", lower), "#2563eb", "Black"),
            (histogram.get("white", upper), "#16a34a", "White"),
        ):
            x = self.preview_histogram_x(value, lower, upper, left, right)
            canvas.create_line(x, top, x, bottom, fill=color, width=3, tags=(f"hist_{label.lower()}", "hist_marker"))
            anchor = "nw" if x < (left + right) / 2 else "ne"
            canvas.create_text(x + (4 if anchor == "nw" else -4), top + 2, text=f"{label}\n{value:.4g}", anchor=anchor, fill=color)
        canvas.create_text(left, bottom + 6, text=f"{lower:.4g}", anchor="nw", fill="#374151")
        canvas.create_text(right, bottom + 6, text=f"{upper:.4g}", anchor="ne", fill="#374151")
        canvas.create_text((left + right) / 2, bottom + 6, text=f"Input intensity • log count • {histogram.get('sampled', 0):,} sampled pixels", anchor="n", fill="#374151")

    def preview_histogram_press(self, event):
        plot = getattr(self, "preview_histogram_plot", None)
        histogram = getattr(self, "preview_histogram_data", {}) or {}
        if not plot or not histogram:
            return
        left, right, lower, upper = plot
        black_x = self.preview_histogram_x(histogram.get("black", lower), lower, upper, left, right)
        white_x = self.preview_histogram_x(histogram.get("white", upper), lower, upper, left, right)
        self.preview_histogram_drag = "black" if abs(event.x - black_x) <= abs(event.x - white_x) else "white"
        self.preview_histogram_drag_motion(event)

    def preview_histogram_drag_motion(self, event):
        marker = getattr(self, "preview_histogram_drag", None)
        plot = getattr(self, "preview_histogram_plot", None)
        histogram = getattr(self, "preview_histogram_data", {}) or {}
        counts = np.asarray(histogram.get("counts", []), dtype=float)
        edges = np.asarray(histogram.get("edges", []), dtype=float)
        if not marker or not plot or not counts.size or edges.size != counts.size + 1:
            return
        left, right, lower, upper = plot
        fraction = min(1.0, max(0.0, (event.x - left) / max(1, right - left)))
        value = lower + fraction * (upper - lower)
        bin_index = min(counts.size - 1, max(0, int(np.searchsorted(edges, value, side="right") - 1)))
        before = float(np.sum(counts[:bin_index]))
        bin_width = max(np.finfo(float).eps, edges[bin_index + 1] - edges[bin_index])
        within = min(1.0, max(0.0, (value - edges[bin_index]) / bin_width))
        percentile = 100.0 * (before + counts[bin_index] * within) / max(1.0, float(np.sum(counts)))
        if marker == "black":
            percentile = min(percentile, float(self.preview_white_percent_var.get()) - 0.01)
            self.preview_black_percent_var.set(f"{max(0, percentile):.3f}")
        else:
            percentile = max(percentile, float(self.preview_black_percent_var.get()) + 0.01)
            self.preview_white_percent_var.set(f"{min(100, percentile):.3f}")
        self.preview_histogram_data[marker] = value
        self.draw_preview_histogram()

    def preview_histogram_release(self, _event=None):
        if getattr(self, "preview_histogram_drag", None):
            self.preview_histogram_drag = None
            self.preview_fits_async()

    def redraw_fits_preview(self, _event=None):
        if hasattr(self, "preview_image"):
            flip_vertical = bool(
                hasattr(self, "preview_flip_vertical_var")
                and self.preview_flip_vertical_var.get()
            )
            display_image = ImageOps.flip(self.preview_image) if flip_vertical else self.preview_image
            canvas = self.preview_canvas
            width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
            fit = min(width / display_image.width, height / display_image.height)
            zoom = max(0.05, float(getattr(self, "preview_view_zoom", 1.0)))
            size = (
                max(1, int(display_image.width * fit * zoom)),
                max(1, int(display_image.height * fit * zoom)),
            )
            rendered = display_image.resize(size, Image.Resampling.LANCZOS)
            from PIL import ImageTk
            self.preview_photo = ImageTk.PhotoImage(rendered)
            canvas.delete("all")
            pan_x, pan_y = getattr(self, "preview_view_pan", (0.0, 0.0))
            center_x, center_y = width / 2 + pan_x, height / 2 + pan_y
            canvas.create_image(center_x, center_y, image=self.preview_photo, anchor="center", tags="preview_image")
            self.preview_render_origin = (center_x - size[0] / 2, center_y - size[1] / 2)
            self.draw_preview_clipping_overlay(display_image, size, self.preview_render_origin)
            self.preview_canvas.delete("preview_cursor")

    def reset_preview_view(self, redraw=True):
        self.preview_view_zoom = 1.0
        self.preview_view_pan = (0.0, 0.0)
        if hasattr(self, "preview_zoom_label_var"):
            self.preview_zoom_label_var.set("Fit")
        if redraw:
            self.redraw_fits_preview()

    def preview_zoom(self, factor, event=None):
        old = float(getattr(self, "preview_view_zoom", 1.0))
        new = min(20.0, max(0.1, old * float(factor)))
        actual_factor = new / old
        if event is not None and hasattr(self, "preview_photo"):
            left, top = getattr(self, "preview_render_origin", (0.0, 0.0))
            old_width, old_height = self.preview_photo.width(), self.preview_photo.height()
            if old_width > 0 and old_height > 0:
                image_fraction_x = (event.x - left) / old_width
                image_fraction_y = (event.y - top) / old_height
                new_width = old_width * actual_factor
                new_height = old_height * actual_factor
                desired_left = event.x - image_fraction_x * new_width
                desired_top = event.y - image_fraction_y * new_height
                canvas_width = max(1, self.preview_canvas.winfo_width())
                canvas_height = max(1, self.preview_canvas.winfo_height())
                self.preview_view_pan = (
                    desired_left + new_width / 2 - canvas_width / 2,
                    desired_top + new_height / 2 - canvas_height / 2,
                )
        self.preview_view_zoom = new
        if hasattr(self, "preview_zoom_label_var"):
            self.preview_zoom_label_var.set(f"{self.preview_view_zoom * 100:.0f}% of fit")
        self.redraw_fits_preview()

    def preview_mousewheel_zoom(self, event):
        self.preview_zoom(1.2 if event.delta > 0 else 1 / 1.2, event)
        return "break"

    def preview_pan_start(self, event):
        self.preview_pan_anchor = (event.x, event.y, *getattr(self, "preview_view_pan", (0.0, 0.0)))

    def preview_pan_motion(self, event):
        anchor = getattr(self, "preview_pan_anchor", None)
        if not anchor:
            return
        self.preview_view_pan = (anchor[2] + event.x - anchor[0], anchor[3] + event.y - anchor[1])
        self.redraw_fits_preview()

    def preview_pan_end(self, _event=None):
        self.preview_pan_anchor = None

    def preview_canvas_display_point(self, canvas_x, canvas_y):
        if not hasattr(self, "preview_photo"):
            return None
        left, top = getattr(self, "preview_render_origin", (0, 0))
        rendered_width, rendered_height = self.preview_photo.width(), self.preview_photo.height()
        if not (
            left <= canvas_x < left + rendered_width
            and top <= canvas_y < top + rendered_height
        ):
            return None
        return (
            min(self.preview_image.width - 1, max(0, int((canvas_x - left) * self.preview_image.width / rendered_width))),
            min(self.preview_image.height - 1, max(0, int((canvas_y - top) * self.preview_image.height / rendered_height))),
        )

    def preview_canvas_motion(self, event):
        if not hasattr(self, "preview_image") or not hasattr(self, "preview_photo"):
            return None
        display_point = self.preview_canvas_display_point(event.x, event.y)
        self.preview_canvas.delete("preview_cursor")
        if display_point is None:
            self.preview_cursor_var.set("Move over the image to inspect pixel and sky coordinates.")
            return None
        flip_vertical = bool(
            hasattr(self, "preview_flip_vertical_var")
            and self.preview_flip_vertical_var.get()
        )
        x, y = self.preview_display_to_source_point(display_point, self.preview_image.size, flip_vertical)
        display_value = self.preview_image.getpixel((x, y))
        details = f"Pixel X {x:,}, Y {y:,}  |  Stretched display value {display_value}"
        wcs = getattr(self, "preview_wcs", None)
        if wcs is not None:
            try:
                ra, dec = wcs.pixel_to_world_values(x, y)
                sky = self.preview_format_sky_position(float(ra), float(dec))
                if sky:
                    details += f"\n{sky}"
            except Exception:
                pass
        self.preview_cursor_var.set(details)
        self.preview_last_cursor_text = details
        if self.preview_crosshair_var.get():
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            rendered_width = self.preview_photo.width()
            rendered_height = self.preview_photo.height()
            left, top = getattr(
                self,
                "preview_render_origin",
                ((canvas_width - rendered_width) / 2.0, (canvas_height - rendered_height) / 2.0),
            )
            display_x, display_y = display_point
            screen_x = left + (display_x + 0.5) * rendered_width / self.preview_image.width
            screen_y = top + (display_y + 0.5) * rendered_height / self.preview_image.height
            self.preview_canvas.create_line(left, screen_y, left + rendered_width, screen_y, fill="#22c55e", tags="preview_cursor")
            self.preview_canvas.create_line(screen_x, top, screen_x, top + rendered_height, fill="#22c55e", tags="preview_cursor")
        return x, y

    def set_preview_sample_mode(self, mode):
        self.preview_sample_mode = mode
        self.convert_status.set(f"Click the image to sample the {mode} level.")

    def preview_primary_click(self, event):
        if getattr(self, "preview_sample_mode", None):
            return self.sample_preview_level(event)
        return self.freeze_preview_probe(event)

    def sample_preview_level(self, event):
        point = self.preview_canvas_display_point(event.x, event.y)
        data = getattr(self, "preview_source_data", None)
        if point is None or data is None:
            return None
        flip = bool(self.preview_flip_vertical_var.get())
        x, y = self.preview_display_to_source_point(point, self.preview_image.size, flip)
        y0, y1 = max(0, y - 2), min(data.shape[0], y + 3)
        x0, x1 = max(0, x - 2), min(data.shape[1], x + 3)
        value = float(np.nanmedian(data[y0:y1, x0:x1]))
        values = np.asarray(data).reshape(-1)
        if values.size > 1_000_000:
            values = values[::max(1, values.size // 1_000_000)]
        finite = values[np.isfinite(values)]
        percentile = float(np.mean(finite <= value) * 100.0)
        mode = self.preview_sample_mode
        if mode == "background":
            self.preview_black_percent_var.set(f"{min(99.98, percentile):.3f}")
        else:
            self.preview_white_percent_var.set(f"{max(0.01, percentile):.3f}")
        self.preview_sample_mode = None
        self.convert_status.set(
            f"Sampled {mode} at X {x}, Y {y}: {value:.7g} ({percentile:.3f} percentile)."
        )
        self.preview_fits_async()
        return x, y

    def draw_preview_clipping_overlay(self, display_image, size, origin):
        arr = np.asarray(display_image.resize(size, Image.Resampling.NEAREST))
        rgba = np.zeros((size[1], size[0], 4), dtype=np.uint8)
        shadow_mask = arr <= 0
        highlight_mask = arr >= 255
        show_shadows = (
            not hasattr(self, "preview_shadow_clipping_var")
            or self.preview_shadow_clipping_var.get()
        )
        show_highlights = (
            not hasattr(self, "preview_highlight_clipping_var")
            or self.preview_highlight_clipping_var.get()
        )
        if show_shadows:
            rgba[shadow_mask] = (37, 99, 235, 105)
        if show_highlights:
            rgba[highlight_mask] = (34, 197, 94, 105)
        if hasattr(self, "preview_clipping_summary_var"):
            total = max(1, arr.size)
            self.preview_clipping_summary_var.set(
                f"Blue shadows {np.count_nonzero(shadow_mask) / total:.2%}  |  "
                f"Green highlights {np.count_nonzero(highlight_mask) / total:.2%}"
            )
        if not np.any(rgba[..., 3]):
            return
        from PIL import ImageTk
        self.preview_clipping_photo = ImageTk.PhotoImage(Image.fromarray(rgba, "RGBA"))
        self.preview_canvas.create_image(
            origin[0],
            origin[1],
            image=self.preview_clipping_photo,
            anchor="nw",
            tags="preview_clipping",
        )

    @staticmethod
    def preview_frozen_probe_text(details, captured_at=""):
        details = str(details or "").strip()
        if not details:
            return "Click a point in the FITS preview to freeze its pixel and sky-coordinate data."
        lines = ["FROZEN PIXEL PROBE", "=" * 44]
        if captured_at:
            lines.append(f"Captured: {captured_at}")
        lines.extend(("", details))
        return "\n".join(lines)

    def freeze_preview_probe(self, event):
        point = self.preview_canvas_motion(event)
        details = getattr(self, "preview_last_cursor_text", "") if point is not None else ""
        if not details:
            return None
        text = self.preview_frozen_probe_text(
            details,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.preview_probe_text.delete("1.0", "end")
        self.preview_probe_text.insert("1.0", text)
        try:
            self.preview_metadata_tabs.select(self.preview_probe_panel)
        except Exception:
            pass
        self.convert_status.set(f"Frozen pixel probe at X {point[0]:,}, Y {point[1]:,}.")
        return point

    def copy_preview_probe(self):
        text = self.preview_probe_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.convert_status.set("Copied frozen pixel probe data.")

    def clear_preview_probe(self, update_status=True):
        if not hasattr(self, "preview_probe_text"):
            return
        self.preview_probe_text.delete("1.0", "end")
        self.preview_probe_text.insert("1.0", self.preview_frozen_probe_text(""))
        if update_status:
            self.convert_status.set("Cleared frozen pixel probe data.")

    def preview_canvas_leave(self, _event=None):
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.delete("preview_cursor")
        if hasattr(self, "preview_cursor_var"):
            self.preview_cursor_var.set("Move over the image to inspect pixel and sky coordinates.")

    def refresh_preview_header_search(self, *_args):
        if not hasattr(self, "header_text"):
            return
        query = self.preview_header_search_var.get() if hasattr(self, "preview_header_search_var") else ""
        text = self.preview_header_text(
            getattr(self, "preview_header", {}),
            query,
            cards=getattr(self, "preview_header_cards", None),
        )
        self.header_text.delete("1.0", "end")
        self.header_text.insert("1.0", text)

    def copy_preview_metadata(self, full_header=False):
        widget = self.header_text if full_header else self.preview_summary_text
        text = widget.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.convert_status.set("Copied FITS header." if full_header else "Copied FITS science summary.")

    @staticmethod
    def avm_metadata_from_header(header):
        return {
            "title": str(header.get("OBJECT") or header.get("TARGNAME") or ""),
            "description": "",
            "creator": str(header.get("ORIGIN") or ""),
            "credit": str(header.get("PI_NAME") or header.get("PR_INV_L") or ""),
            "rights": "",
            "subject": str(header.get("OBJECT") or header.get("TARGNAME") or ""),
            "facility": str(header.get("TELESCOP") or ""),
            "instrument": str(header.get("INSTRUME") or ""),
            "spectral_band": str(header.get("FILTER") or header.get("FILTER1") or ""),
        }

    @staticmethod
    def avm_xmp_packet(metadata):
        value = lambda key: escape(str(metadata.get(key, "") or ""), {'"': "&quot;"})
        return f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:avm="http://www.communicatingastronomy.org/avm/1.0/">
      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{value("title")}</rdf:li></rdf:Alt></dc:title>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{value("description")}</rdf:li></rdf:Alt></dc:description>
      <dc:creator><rdf:Seq><rdf:li>{value("creator")}</rdf:li></rdf:Seq></dc:creator>
      <dc:rights><rdf:Alt><rdf:li xml:lang="x-default">{value("rights")}</rdf:li></rdf:Alt></dc:rights>
      <dc:subject><rdf:Bag><rdf:li>{value("subject")}</rdf:li></rdf:Bag></dc:subject>
      <avm:MetadataVersion>1.2</avm:MetadataVersion>
      <avm:Credit>{value("credit")}</avm:Credit>
      <avm:Facility>{value("facility")}</avm:Facility>
      <avm:Instrument>{value("instrument")}</avm:Instrument>
      <avm:SpectralBand>{value("spectral_band")}</avm:SpectralBand>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

    def load_avm_from_fits(self):
        values = self.avm_metadata_from_header(getattr(self, "preview_header", {}))
        for key, var in getattr(self, "preview_avm_vars", {}).items():
            var.set(values.get(key, ""))
        self.convert_status.set("Loaded available publication metadata from the current FITS header.")

    def save_avm_metadata(self):
        path = self.convert_path_var.get().strip()
        if not path:
            messagebox.showinfo("AVM Metadata", "Choose and preview a FITS file first.")
            return
        payload = {
            "avm_version": "1.2",
            **{key: var.get().strip() for key, var in self.preview_avm_vars.items()},
        }
        output = Path(path).with_suffix(".avm.json")
        xmp_output = Path(path).with_suffix(".xmp")
        try:
            output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            xmp_output.write_text(self.avm_xmp_packet(payload), encoding="utf-8")
        except Exception as exc:
            self.convert_status.set(f"AVM metadata save failed: {exc}")
            return
        self.convert_status.set(
            f"Saved publication sidecars: {xmp_output.name} and {output.name}"
        )

    def save_preview_outputs(self):
        if not hasattr(self, "preview_image"):
            messagebox.showinfo("Save", "Preview a FITS file first.")
            return
        try:
            bit_depth = int(self.preview_export_bit_depth_var.get())
            if bit_depth not in (8, 16):
                raise ValueError
        except (TypeError, ValueError):
            self.convert_status.set("Choose either 8-bit or 16-bit preview export.")
            return
        base = OUTPUT_DIR / f"{self.output_prefix()}_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        png_path = base.with_suffix(".png")
        tif_path = base.with_suffix(".tif")
        if bit_depth == 8:
            self.preview_image.save(png_path)
            self.preview_image.save(tif_path)
            self.convert_status.set(f"Saved 8-bit {png_path.name} and {tif_path.name}")
            return
        path = self.convert_path_var.get().strip()
        if not path:
            self.convert_status.set("The original FITS path is required for a true 16-bit export.")
            return
        try:
            black_percent, white_percent = self.preview_stretch_percentiles(
                self.preview_black_percent_var.get(),
                self.preview_white_percent_var.get(),
            )
        except ValueError as exc:
            self.convert_status.set(f"16-bit export settings need attention: {exc}")
            return
        stretch = self.stretch_var.get()
        self.convert_status.set("Creating true 16-bit PNG and TIFF from FITS data...")

        def worker():
            try:
                hdu_index = getattr(self, "preview_selected_hdu_index", None)
                plane_index = int(self.preview_plane_var.get()) if hasattr(self, "preview_plane_var") else 0
                data, _header, _cards, _inventory = first_image_hdu_details(
                    path,
                    hdu_index,
                    plane_index,
                )
                normalized = normalize_image_uint16(
                    data,
                    low_percent=black_percent,
                    high_percent=white_percent,
                    stretch=stretch,
                )
                image = Image.fromarray(normalized, mode="I;16")
                image.save(png_path)
                image.save(tif_path)
                result = (png_path, tif_path, None)
            except Exception as exc:
                result = (png_path, tif_path, exc)
            self.after(0, lambda: self.finish_save_preview_outputs(result, bit_depth))

        threading.Thread(target=worker, daemon=True).start()

    def finish_save_preview_outputs(self, result, bit_depth):
        png_path, tif_path, error = result
        if error:
            self.convert_status.set(f"{bit_depth}-bit preview export failed: {error}")
            return
        self.convert_status.set(f"Saved {bit_depth}-bit {png_path.name} and {tif_path.name}")

    def choose_channel(self, var):
        path = filedialog.askopenfilename(
            title="Choose FITS Channel",
            initialdir=str(DOWNLOAD_DIR),
            filetypes=[("FITS files", "*.fits *.fits.gz *.fit"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    @staticmethod
    def channel_score(path, tokens):
        name = path.name.upper()
        for score, token in enumerate(tokens):
            if token in name:
                return score
        return None

    @staticmethod
    def rgb_filename_tokens():
        return {
            "blue": ("F070W", "F090W", "F115W", "F150W", "F435W", "F438W", "F439W", "F450W", "F475W", "F336W", "F275W"),
            "green": ("F200W", "F277W", "F300M", "F335M", "F555W", "F606W", "F547M", "F550M", "F502N", "F625W"),
            "red": ("F356W", "F444W", "F560W", "F770W", "F1000W", "F1130W", "F1280W", "F1500W", "F814W", "F850LP", "F775W", "F675W", "F658N", "F656N", "F160W", "F140W", "F125W", "F110W", "F105W"),
        }

    def find_latest_rgb_folder(self):
        folders = [
            path for path in DOWNLOAD_DIR.glob("*RGB_set/*")
            if path.is_dir()
        ]
        if not folders:
            return None
        return max(folders, key=lambda path: path.stat().st_mtime)

    def pick_rgb_files_from_folder(self, folder):
        files = [
            path for path in folder.iterdir()
            if path.is_file() and path.name.lower().endswith((".fits", ".fits.gz", ".fit"))
        ]
        channels = self.rgb_filename_tokens()
        picks = {}
        for channel, tokens in channels.items():
            scored = []
            for path in files:
                score = self.channel_score(path, tokens)
                if score is not None:
                    scored.append((score, path.name.upper(), path))
            if scored:
                picks[channel] = sorted(scored)[0][2]
        return picks

    def load_latest_rgb_set(self):
        folder = self.find_latest_rgb_folder()
        if not folder:
            messagebox.showinfo("Load Latest RGB Set", "No downloaded RGB set folder was found yet.")
            return
        picks = self.pick_rgb_files_from_folder(folder)
        missing = [channel for channel in ("blue", "green", "red") if channel not in picks]
        if missing:
            messagebox.showinfo(
                "Load Latest RGB Set",
                f"I found the latest RGB folder, but could not identify: {', '.join(missing)}.",
            )
            return
        self.blue_path_var.set(str(picks["blue"]))
        self.green_path_var.set(str(picks["green"]))
        self.red_path_var.set(str(picks["red"]))
        self.compose_status.set(f"Loading RGB channels from {folder.name}...")
        self.compose_progress.start(12)
        self.update_idletasks()
        self.preview_channel_thumbnails_async(picks, folder)

    def preview_channel_thumbnails(self, picks):
        if FITS is None:
            return {}
        thumbnails = {}
        for channel, path in picks.items():
            try:
                data, _header = first_image_hdu(path)
                data = downsample_array_for_preview(data)
                image = Image.fromarray(normalize_image(data, stretch=self.compose_stretch_var.get()), mode="L")
                thumbnails[channel] = image
            except Exception:
                pass
        return thumbnails

    def preview_channel_thumbnails_async(self, picks, folder=None, compose_after=None):
        if not self.require_astropy():
            return
        if compose_after is None:
            compose_after = bool(self.auto_compose_var.get())

        def worker():
            try:
                thumbnails = self.preview_channel_thumbnails(picks)
                error = None
            except Exception as exc:
                thumbnails = {}
                error = exc
            self.after(0, lambda: self.finish_channel_thumbnails(thumbnails, folder, error, compose_after))

        threading.Thread(target=worker, daemon=True).start()

    def finish_channel_thumbnails(self, thumbnails, folder=None, error=None, compose_after=False):
        for channel, image in thumbnails.items():
            self.show_image_on_canvas(self.channel_thumbnail_canvases[channel], image, f"{channel}_thumb_photo")
        if error:
            self.compose_status.set(f"Loaded RGB set, but channel previews failed: {error}")
        elif folder:
            self.compose_status.set(f"Loaded latest RGB set from {folder}")
        else:
            self.compose_status.set("RGB channel previews loaded.")
        if compose_after and all(
            path.strip() for path in (self.red_path_var.get(), self.green_path_var.get(), self.blue_path_var.get())
        ):
            self.compose_async()
        else:
            self.compose_progress.stop()
