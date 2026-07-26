import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import numpy as np
from PIL import Image

from .fits_io import FITS, first_image_hdu
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
    def preview_header_text(header, query=""):
        query = str(query or "").strip().lower()
        rows = []
        for key, value in header.items():
            line = f"{key:<10} = {value}"
            if not query or query in line.lower():
                rows.append(line)
        return "\n".join(rows) if rows else "No FITS header fields match the current search."

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
        self.convert_status.set("Reading FITS image...")

        def worker():
            try:
                data, header = first_image_hdu(path)
                statistics = self.preview_image_statistics(data)
                normalized = normalize_image(data, stretch=self.stretch_var.get())
                result = (normalized, header, statistics, path, None)
            except Exception as exc:
                result = (None, {}, {}, path, exc)
            self.after(0, lambda: self.finish_preview(result))

        threading.Thread(target=worker, daemon=True).start()

    def finish_preview(self, result):
        if len(result) == 3:
            image, header, error = result
            statistics, path = {}, self.convert_path_var.get().strip()
        else:
            image, header, statistics, path, error = result
        if error:
            self.convert_status.set(f"Preview failed: {error}")
            return
        self.preview_image = Image.fromarray(image, mode="L")
        self.preview_header = dict(header)
        self.preview_statistics = dict(statistics)
        self.show_image_on_canvas(self.preview_canvas, self.preview_image, "preview_photo")
        summary = self.preview_metadata_summary(header, self.preview_image.size[::-1], statistics, path)
        self.preview_summary_text.delete("1.0", "end")
        self.preview_summary_text.insert("1.0", summary)
        self.refresh_preview_header_search()
        self.convert_status.set(f"Preview loaded at {self.preview_image.width} x {self.preview_image.height}px. Display is scaled to fit the canvas.")

    def refresh_preview_header_search(self, *_args):
        if not hasattr(self, "header_text"):
            return
        query = self.preview_header_search_var.get() if hasattr(self, "preview_header_search_var") else ""
        text = self.preview_header_text(getattr(self, "preview_header", {}), query)
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
