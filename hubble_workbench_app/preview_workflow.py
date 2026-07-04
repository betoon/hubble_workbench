import threading
from datetime import datetime
from tkinter import filedialog, messagebox

from PIL import Image

from .fits_io import FITS, first_image_hdu
from .image_processing import downsample_array_for_preview, normalize_image
from .paths import DOWNLOAD_DIR, OUTPUT_DIR


class PreviewWorkflowMixin:
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
                normalized = normalize_image(data, stretch=self.stretch_var.get())
                result = (normalized, header, None)
            except Exception as exc:
                result = (None, {}, exc)
            self.after(0, lambda: self.finish_preview(result))

        threading.Thread(target=worker, daemon=True).start()

    def finish_preview(self, result):
        image, header, error = result
        if error:
            self.convert_status.set(f"Preview failed: {error}")
            return
        self.preview_image = Image.fromarray(image, mode="L")
        self.show_image_on_canvas(self.preview_canvas, self.preview_image, "preview_photo")
        self.header_text.delete("1.0", "end")
        for key in ("TELESCOP", "INSTRUME", "DETECTOR", "FILTER", "FILTER1", "FILTER2", "EXPTIME", "DATE-OBS", "TARGNAME"):
            if key in header:
                self.header_text.insert("end", f"{key}: {header[key]}\n")
        self.convert_status.set(f"Preview loaded at {self.preview_image.width} x {self.preview_image.height}px. Display is scaled to fit the canvas.")

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
