import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import numpy as np
from PIL import Image, ImageOps

from .fits_io import FITS, _celestial_wcs, first_image_hdu, first_image_hdu_details
from .image_processing import downsample_array_for_preview, normalize_image
from .paths import DOWNLOAD_DIR, OUTPUT_DIR


class PreviewWorkflowMixin:
    PREVIEW_METADATA_GROUPS = (
        ("File and Image", ("FILENAME", "EXTNAME", "NAXIS1", "NAXIS2", "BITPIX", "BUNIT")),
        ("Target and Observation", ("TARGNAME", "OBJECT", "TELESCOP", "INSTRUME", "DETECTOR", "FILTER", "FILTER1", "FILTER2", "EXPTIME", "DATE-OBS", "TIME-OBS", "PROPOSID", "PROGRAM")),
        ("World Coordinates", ("RADESYS", "RADECSYS", "EQUINOX", "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CDELT1", "CDELT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2")),
    )

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
        self.convert_status.set("Reading FITS image...")

        def worker():
            try:
                data, header, cards, inventory = first_image_hdu_details(path)
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
                result = (normalized, header, statistics, histogram, cards, inventory, path, None)
            except Exception as exc:
                result = (None, {}, {}, {}, [], [], path, exc)
            self.after(0, lambda: self.finish_preview(result))

        threading.Thread(target=worker, daemon=True).start()

    def reset_preview_stretch(self):
        self.preview_black_percent_var.set("0.5")
        self.preview_white_percent_var.set("99.5")
        self.convert_status.set("Restored automatic black and white points. Select Apply Stretch to refresh the preview.")

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
        else:
            image, header, statistics, histogram, cards, inventory, path, error = result
        if error:
            self.convert_status.set(f"Preview failed: {error}")
            return
        self.preview_image = Image.fromarray(image, mode="L")
        self.preview_header = dict(header)
        self.preview_statistics = dict(statistics)
        self.preview_histogram_data = dict(histogram)
        self.preview_header_cards = list(cards)
        self.preview_hdu_inventory = list(inventory)
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
        self.convert_status.set(f"Preview loaded at {self.preview_image.width} x {self.preview_image.height}px. Display is scaled to fit the canvas.")

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
        for value, color, label in (
            (histogram.get("black", lower), "#2563eb", "Black"),
            (histogram.get("white", upper), "#16a34a", "White"),
        ):
            x = self.preview_histogram_x(value, lower, upper, left, right)
            canvas.create_line(x, top, x, bottom, fill=color, width=2)
            anchor = "nw" if x < (left + right) / 2 else "ne"
            canvas.create_text(x + (4 if anchor == "nw" else -4), top + 2, text=f"{label}\n{value:.4g}", anchor=anchor, fill=color)
        canvas.create_text(left, bottom + 6, text=f"{lower:.4g}", anchor="nw", fill="#374151")
        canvas.create_text(right, bottom + 6, text=f"{upper:.4g}", anchor="ne", fill="#374151")
        canvas.create_text((left + right) / 2, bottom + 6, text=f"Input intensity • log count • {histogram.get('sampled', 0):,} sampled pixels", anchor="n", fill="#374151")

    def redraw_fits_preview(self, _event=None):
        if hasattr(self, "preview_image"):
            flip_vertical = bool(
                hasattr(self, "preview_flip_vertical_var")
                and self.preview_flip_vertical_var.get()
            )
            display_image = ImageOps.flip(self.preview_image) if flip_vertical else self.preview_image
            self.show_image_on_canvas(self.preview_canvas, display_image, "preview_photo")
            self.preview_canvas.delete("preview_cursor")

    def preview_canvas_motion(self, event):
        if not hasattr(self, "preview_image") or not hasattr(self, "preview_photo"):
            return None
        display_point = self.preview_canvas_to_image_point(
            event.x,
            event.y,
            (max(1, self.preview_canvas.winfo_width()), max(1, self.preview_canvas.winfo_height())),
            (self.preview_photo.width(), self.preview_photo.height()),
            self.preview_image.size,
        )
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
        if self.preview_crosshair_var.get():
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            rendered_width = self.preview_photo.width()
            rendered_height = self.preview_photo.height()
            left = (canvas_width - rendered_width) / 2.0
            top = (canvas_height - rendered_height) / 2.0
            display_x, display_y = display_point
            screen_x = left + (display_x + 0.5) * rendered_width / self.preview_image.width
            screen_y = top + (display_y + 0.5) * rendered_height / self.preview_image.height
            self.preview_canvas.create_line(left, screen_y, left + rendered_width, screen_y, fill="#22c55e", tags="preview_cursor")
            self.preview_canvas.create_line(screen_x, top, screen_x, top + rendered_height, fill="#22c55e", tags="preview_cursor")
        return point

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

    def save_preview_outputs(self):
        if not hasattr(self, "preview_image"):
            messagebox.showinfo("Save", "Preview a FITS file first.")
            return
        base = OUTPUT_DIR / f"{self.output_prefix()}_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        png_path = base.with_suffix(".png")
        tif_path = base.with_suffix(".tif")
        self.preview_image.save(png_path)
        self.preview_image.save(tif_path)
        self.convert_status.set(f"Saved {png_path.name} and {tif_path.name}")

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
