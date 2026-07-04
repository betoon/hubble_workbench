import json
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import tifffile
except Exception:
    tifffile = None

from .image_processing import float_rgb_to_uint16
from .paths import APP_DIR, NOTES_DIR, OUTPUT_DIR


class ProjectWorkflowMixin:
    def auto_save_preview_png(self):
        if not hasattr(self, "rgb_image"):
            return None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"{self.output_prefix()}_rgb_preview_{stamp}.png"
        try:
            self.rgb_image.save(path)
            self.last_output_path = path
            return path
        except Exception:
            return None

    def project_state(self):
        return {
            "target": self.target_var.get(),
            "radius": self.radius_var.get(),
            "stretch": self.compose_stretch_var.get(),
            "red": self.red_path_var.get(),
            "green": self.green_path_var.get(),
            "blue": self.blue_path_var.get(),
            "composite_size": self.composite_size_var.get(),
            "high_quality_processing": bool(self.high_quality_var.get()),
            "prefer_drizzled_products": bool(self.prefer_drizzled_var.get()),
            "use_fits_liberator_engine": bool(self.use_fits_liberator_var.get()),
            "presentation_cleanup": bool(self.presentation_cleanup_var.get()),
            "straighten_angle": float(self.straighten_angle_var.get()),
            "auto_crop_presentation": bool(self.auto_crop_presentation_var.get()),
            "advanced_stretch": {
                channel: {
                    "low": values["low"].get(),
                    "high": values["high"].get(),
                    "gamma": values["gamma"].get(),
                    "asinh": values["asinh"].get(),
                }
                for channel, values in self.channel_stretch_vars.items()
            },
            "auto_compose_after_load": bool(self.auto_compose_var.get()),
            "tuning": {
                "black_point": self.black_point_var.get(),
                "brightness": self.brightness_var.get(),
                "contrast": self.contrast_var.get(),
                "saturation": self.saturation_var.get(),
                "red_balance": self.red_balance_var.get(),
                "green_balance": self.green_balance_var.get(),
                "blue_balance": self.blue_balance_var.get(),
            },
            "saved": datetime.now().isoformat(timespec="seconds"),
        }

    def apply_project_state(self, data):
        self.target_var.set(data.get("target", self.target_var.get()))
        self.radius_var.set(data.get("radius", self.radius_var.get()))
        self.compose_stretch_var.set(data.get("stretch", self.compose_stretch_var.get()))
        self.red_path_var.set(data.get("red", ""))
        self.green_path_var.set(data.get("green", ""))
        self.blue_path_var.set(data.get("blue", ""))
        self.composite_size_var.set(data.get("composite_size", self.composite_size_var.get()))
        self.high_quality_var.set(bool(data.get("high_quality_processing", self.high_quality_var.get())))
        self.prefer_drizzled_var.set(bool(data.get("prefer_drizzled_products", self.prefer_drizzled_var.get())))
        self.use_fits_liberator_var.set(bool(data.get("use_fits_liberator_engine", self.use_fits_liberator_var.get())))
        self.presentation_cleanup_var.set(bool(data.get("presentation_cleanup", self.presentation_cleanup_var.get())))
        self.straighten_angle_var.set(float(data.get("straighten_angle", self.straighten_angle_var.get())))
        self.auto_crop_presentation_var.set(bool(data.get("auto_crop_presentation", self.auto_crop_presentation_var.get())))
        if hasattr(self, "straighten_label"):
            self.straighten_label.configure(text=f"{self.straighten_angle_var.get():.1f} deg")
        advanced = data.get("advanced_stretch", {})
        for channel, values in advanced.items():
            if channel in self.channel_stretch_vars:
                self.channel_stretch_vars[channel]["low"].set(float(values.get("low", self.channel_stretch_vars[channel]["low"].get())))
                self.channel_stretch_vars[channel]["high"].set(float(values.get("high", self.channel_stretch_vars[channel]["high"].get())))
                self.channel_stretch_vars[channel]["gamma"].set(float(values.get("gamma", self.channel_stretch_vars[channel]["gamma"].get())))
                self.channel_stretch_vars[channel]["asinh"].set(float(values.get("asinh", self.channel_stretch_vars[channel]["asinh"].get())))
        self.auto_compose_var.set(bool(data.get("auto_compose_after_load", self.auto_compose_var.get())))
        tuning = data.get("tuning", {})
        self.black_point_var.set(float(tuning.get("black_point", self.black_point_var.get())))
        self.brightness_var.set(float(tuning.get("brightness", self.brightness_var.get())))
        self.contrast_var.set(float(tuning.get("contrast", self.contrast_var.get())))
        self.saturation_var.set(float(tuning.get("saturation", self.saturation_var.get())))
        self.red_balance_var.set(float(tuning.get("red_balance", self.red_balance_var.get())))
        self.green_balance_var.set(float(tuning.get("green_balance", self.green_balance_var.get())))
        self.blue_balance_var.set(float(tuning.get("blue_balance", self.blue_balance_var.get())))
        self.compose_status.set("Project loaded.")

    def save_project_file(self):
        path = filedialog.asksaveasfilename(
            title="Save Space Telescope Project",
            initialdir=str(APP_DIR),
            defaultextension=".json",
            filetypes=[("Space telescope project", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(json.dumps(self.project_state(), indent=2), encoding="utf-8")
        self.compose_status.set(f"Saved project {Path(path).name}.")

    def open_project_file(self):
        path = filedialog.askopenfilename(
            title="Open Space Telescope Project",
            initialdir=str(APP_DIR),
            filetypes=[("Space telescope project", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.apply_project_state(data)
        except Exception as exc:
            messagebox.showinfo("Open Project", f"Could not open project: {exc}")

    def open_latest_output(self):
        candidates = sorted(
            list(OUTPUT_DIR.glob("*.png")) + list(OUTPUT_DIR.glob("*.tif")) + list(OUTPUT_DIR.glob("*.tiff")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        path = self.last_output_path if self.last_output_path and self.last_output_path.exists() else (candidates[0] if candidates else None)
        if not path:
            messagebox.showinfo("Open Latest Output", "No saved output image was found yet.")
            return
        try:
            import os
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("Open Latest Output", str(path))

    def save_composite_outputs(self):
        if not hasattr(self, "rgb_image"):
            messagebox.showinfo("Save Composite", "Compose an RGB image first.")
            return
        output_image = self.rgb_image
        output_float = getattr(self, "rgb_float_image", None)
        output_fills = getattr(self, "presentation_cleanup_fills", 0)
        if hasattr(self, "rgb_full_base_image"):
            self.compose_status.set("Rendering full-size output...")
            self.update_idletasks()
            output_image, output_float, output_fills = self.render_tuned_image(
                self.rgb_full_base_image,
                getattr(self, "rgb_full_base_float", None),
            )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = self.output_prefix()
        png_path = OUTPUT_DIR / f"{prefix}_rgb_{stamp}.png"
        tif_path = OUTPUT_DIR / f"{prefix}_rgb_{stamp}.tif"
        notes_path = NOTES_DIR / f"{prefix}_rgb_{stamp}_notes.txt"
        output_image.save(png_path)
        saved_16bit = False
        if output_float is not None and tifffile is not None and output_float.shape[:2] == (output_image.height, output_image.width):
            tifffile.imwrite(str(tif_path), float_rgb_to_uint16(output_float), photometric="rgb")
            saved_16bit = True
        else:
            output_image.save(tif_path)
        notes = [
            f"{self.telescope_var.get()} RGB Composite",
            f"Created: {datetime.now().isoformat(timespec='seconds')}",
            f"Target: {self.target_var.get()}",
            f"Stretch: {self.compose_stretch_var.get()}",
            f"High quality processing: {getattr(self, 'rgb_base_float', None) is not None}",
            f"TIFF bit depth: {'16-bit per channel' if saved_16bit else '8-bit per channel'}",
            f"Composite size mode: {getattr(self, 'rgb_resize_mode', self.composite_size_var.get())}",
            f"Presentation cleanup: {bool(self.presentation_cleanup_var.get())}",
            f"Presentation cleanup fills: {output_fills}",
            f"Straighten angle: {self.straighten_angle_var.get():.2f} deg",
            f"Auto crop black border: {bool(self.auto_crop_presentation_var.get())}",
            f"Output pixels: {output_image.width} x {output_image.height}",
            "",
            "Processing settings:",
            f"Black point: {self.black_point_var.get():.2f}",
            f"Brightness: {self.brightness_var.get():.2f}",
            f"Contrast: {self.contrast_var.get():.2f}",
            f"Saturation: {self.saturation_var.get():.2f}",
            f"Red balance: {self.red_balance_var.get():.2f}",
            f"Green balance: {self.green_balance_var.get():.2f}",
            f"Blue balance: {self.blue_balance_var.get():.2f}",
            "",
            "Advanced stretch settings:",
        ]
        if hasattr(self, "channel_stretch_vars"):
            for channel in ("red", "green", "blue"):
                values = self.channel_stretch_vars[channel]
                notes.append(
                    f"{channel.title()}: low {values['low'].get():.2f}%, high {values['high'].get():.2f}%, "
                    f"gamma {values['gamma'].get():.2f}, asinh {values['asinh'].get():.2f}"
                )
        notes.extend([
            "",
            f"Red: {self.red_path_var.get()}",
            f"Green: {self.green_path_var.get()}",
            f"Blue: {self.blue_path_var.get()}",
            "",
            "Filter hints from headers:",
        ])
        for label, header in zip(("Red", "Green", "Blue"), getattr(self, "rgb_headers", [])):
            filters = [str(header.get(key, "")) for key in ("FILTER", "FILTER1", "FILTER2") if header.get(key)]
            notes.append(f"{label}: {', '.join(filters) or 'not listed'}")
        notes_path.write_text("\n".join(notes), encoding="utf-8")
        self.last_output_path = png_path
        bit_note = "16-bit TIFF" if saved_16bit else "8-bit TIFF"
        self.compose_status.set(f"Saved {png_path.name}, {tif_path.name} ({bit_note}), and notes.")
