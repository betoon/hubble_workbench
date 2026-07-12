import tempfile
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import numpy as np
from PIL import Image

from .fits_io import find_fits_liberator_cli, first_image_hdu, run_fits_liberator_channel
from .image_processing import (
    downsample_float_rgb_for_preview,
    downsample_image_for_preview,
    fill_internal_black_gaps,
    float_rgb_to_uint8,
    normalize_float_channel,
    normalize_image,
    presentation_transform,
    resize_float_to_match,
    resize_to_match,
)
from .paths import NOTES_DIR, RGB_PRESET_PREVIEW_MAX_PIXELS


class ComposeWorkflowMixin:
    def compose_async(self):
        if not self.require_astropy():
            return
        paths = [self.red_path_var.get().strip(), self.green_path_var.get().strip(), self.blue_path_var.get().strip()]
        if any(not path for path in paths):
            messagebox.showinfo("Compose RGB", "Choose red, green, and blue FITS files.")
            return
        self.compose_status.set("Composing RGB image in the background...")
        self.compose_progress.start(12)
        self.update_idletasks()

        def worker():
            try:
                image, headers, source_shapes, resize_mode, rgb_float, engine_note = self.compose_rgb_from_paths(paths)
                base_image, base_float = self.prepare_compose_working_copy(image, rgb_float)
                result = (image, headers, source_shapes, resize_mode, rgb_float, engine_note, base_image, base_float, None)
            except Exception as exc:
                result = (None, [], [], "", None, "", None, None, exc)
            self.after(0, lambda: self.finish_compose(result))

        threading.Thread(target=worker, daemon=True).start()

    def prepare_compose_working_copy(self, image, rgb_float):
        if rgb_float is not None:
            base_float = downsample_float_rgb_for_preview(rgb_float)
            base_image = Image.fromarray(float_rgb_to_uint8(base_float), mode="RGB")
            return base_image, base_float
        return downsample_image_for_preview(image), None

    def compose_rgb_from_paths(self, paths):
        if getattr(self, "use_fits_liberator_var", None) is not None and self.use_fits_liberator_var.get():
            cli_path = find_fits_liberator_cli()
            if cli_path:
                try:
                    return self.compose_rgb_with_fits_liberator(paths, cli_path)
                except Exception as exc:
                    self.after(0, lambda e=exc: self.compose_status.set(f"FITS Liberator unavailable for this set; using Python engine. {e}"))
        channels = []
        headers = []
        source_shapes = []
        high_quality = bool(self.high_quality_var.get())
        channel_names = ("red", "green", "blue")
        for channel_name, path in zip(channel_names, paths):
            self.after(0, lambda c=channel_name, p=path: self.compose_status.set(f"Reading {c} channel: {Path(p).name}"))
            data, header = first_image_hdu(path)
            source_shapes.append(data.shape)
            self.after(0, lambda c=channel_name: self.compose_status.set(f"Stretching {c} channel..."))
            if high_quality:
                settings = self.channel_stretch_vars[channel_name]
                low = float(settings["low"].get())
                high = float(settings["high"].get())
                if high <= low:
                    high = low + 0.1
                channels.append(normalize_float_channel(
                    data,
                    low_percent=low,
                    high_percent=high,
                    stretch=self.compose_stretch_var.get(),
                    gamma=float(settings["gamma"].get()),
                    asinh_strength=float(settings["asinh"].get()),
                ))
            else:
                channels.append(normalize_image(data, stretch=self.compose_stretch_var.get()))
            headers.append(header)
        self.after(0, lambda: self.compose_status.set("Combining RGB channels..."))
        resize_mode = "largest" if self.composite_size_var.get() == "Largest channel" else "smallest"
        if high_quality:
            r, g, b = resize_float_to_match(channels, resize_mode)
            rgb_float = np.dstack([r, g, b]).astype(np.float32)
            image = Image.fromarray(float_rgb_to_uint8(rgb_float), mode="RGB")
            return image, headers, source_shapes, resize_mode, rgb_float, "Python engine"
        r, g, b = resize_to_match(channels, resize_mode)
        rgb = np.dstack([r, g, b]).astype(np.uint8)
        return Image.fromarray(rgb, mode="RGB"), headers, source_shapes, resize_mode, None, "Python engine"

    def compose_rgb_with_fits_liberator(self, paths, cli_path):
        channels = []
        headers = []
        source_shapes = []
        channel_names = ("red", "green", "blue")
        stretch = self.compose_stretch_var.get()
        with tempfile.TemporaryDirectory(prefix="hubble_fitslib_") as temp_dir:
            temp_dir = Path(temp_dir)
            for channel_name, path in zip(channel_names, paths):
                self.after(0, lambda c=channel_name, p=path: self.compose_status.set(f"Preparing {c} channel for FITS Liberator: {Path(p).name}"))
                data, header = first_image_hdu(path)
                source_shapes.append(data.shape)
                headers.append(header)
                settings = self.channel_stretch_vars[channel_name]
                low_percent = float(settings["low"].get())
                high_percent = float(settings["high"].get())
                if high_percent <= low_percent:
                    high_percent = low_percent + 0.1
                finite = np.asarray(data, dtype=np.float64)
                finite = finite[np.isfinite(finite)]
                if finite.size == 0:
                    raise RuntimeError(f"{Path(path).name} has no finite pixels.")
                low, high = np.nanpercentile(finite, [low_percent, high_percent])
                if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                    low, high = np.nanmin(finite), np.nanmax(finite)
                if high <= low:
                    channels.append(np.zeros(data.shape, dtype=np.float32))
                    continue
                output_path = temp_dir / f"{channel_name}.tif"
                self.after(0, lambda c=channel_name: self.compose_status.set(f"FITS Liberator is processing {c} channel..."))
                channel = run_fits_liberator_channel(
                    cli_path,
                    path,
                    output_path,
                    low,
                    high,
                    stretch,
                    gamma=float(settings["gamma"].get()),
                    asinh_strength=float(settings["asinh"].get()),
                )
                channels.append(channel)
        self.after(0, lambda: self.compose_status.set("Combining FITS Liberator RGB channels..."))
        resize_mode = "largest" if self.composite_size_var.get() == "Largest channel" else "smallest"
        r, g, b = resize_float_to_match(channels, resize_mode)
        rgb_float = np.dstack([r, g, b]).astype(np.float32)
        image = Image.fromarray(float_rgb_to_uint8(rgb_float), mode="RGB")
        return image, headers, source_shapes, resize_mode, rgb_float, f"FITS Liberator engine ({Path(cli_path).name})"

    def finish_compose(self, result):
        self.compose_progress.stop()
        image, headers, source_shapes, resize_mode, rgb_float, engine_note, base_image, base_float, error = result
        if error:
            self.compose_status.set(f"RGB compose failed: {error}")
            if hasattr(self, "set_easy_all_sensors_status") and getattr(self, "easy_all_sensors_pending_stage", None) == "compose":
                self.set_easy_all_sensors_status("stopped", f"RGB compose failed: {error}")
                self.save_easy_all_sensors_status_snapshot()
                self.easy_all_sensors_pending_stage = None
            return
        self.rgb_full_base_image = image
        self.rgb_full_base_float = rgb_float
        self.rgb_base_image = base_image
        self.rgb_base_float = base_float
        self.rgb_headers = headers
        self.rgb_source_shapes = source_shapes
        self.rgb_resize_mode = resize_mode
        self.compose_status.set("Preparing RGB preview...")
        self.update_idletasks()
        self.apply_image_tuning()
        size_text = f"{image.width} x {image.height}px"
        if self.rgb_base_image.size != image.size:
            size_text += f" (preview tuned at {self.rgb_base_image.width} x {self.rgb_base_image.height}px)"
        engine_text = f" using {engine_note}" if engine_note else ""
        self.compose_status.set(f"RGB preview ready at {size_text}{engine_text}. Finishing small preview extras...")
        self.after(50, lambda: self.finish_compose_extras(size_text, engine_text))

    def finish_compose_extras(self, size_text, engine_text):
        self.generate_preset_previews()
        preview_path = self.auto_save_preview_png()
        if hasattr(self, "set_easy_all_sensors_status") and getattr(self, "easy_all_sensors_pending_stage", None) == "compose":
            detail = f"Composite ready at {size_text}{engine_text}."
            if preview_path:
                self.easy_all_sensors_latest_preview_path = str(preview_path)
                detail += f" Auto-saved {preview_path.name}."
            else:
                self.easy_all_sensors_latest_preview_path = ""
            self.set_easy_all_sensors_status("complete", detail)
            try:
                self.save_easy_all_sensors_summary(update_ui=False)
            except Exception:
                pass
            self.easy_all_sensors_pending_stage = None
        if preview_path:
            self.compose_status.set(f"RGB composite ready at {size_text}{engine_text}. Auto-saved {preview_path.name}.")
        else:
            self.compose_status.set(f"RGB composite ready at {size_text}{engine_text}.")

    def finish_easy_rgb(self, operation_id, result, error, error_detail=None):
        if operation_id != self.browser_operation_id:
            return
        if error:
            log_message = ""
            if error_detail:
                try:
                    NOTES_DIR.mkdir(parents=True, exist_ok=True)
                    log_path = NOTES_DIR / f"easy_rgb_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    log_path.write_text(error_detail, encoding="utf-8")
                    log_message = f" Details saved to {log_path.name}."
                except Exception:
                    pass
            self.stop_browser_activity(f"Easy RGB failed: {error}.{log_message}")
            return
        self.search_results = result["obs_rows"]
        self.product_results = result["products"]
        self.obs_list.delete(0, "end")
        for row in self.search_results[:500]:
            label = (
                f"{row.get('obs_collection', '')} | {row.get('obs_id', '')} | {row.get('instrument_name', '')} | "
                f"{row.get('filters', '')} | {row.get('t_exptime', '')}s"
            )
            self.obs_list.insert("end", label)
        obs_index = self.search_results.index(result["obs"]) if result["obs"] in self.search_results else 0
        if self.obs_list.size():
            self.obs_list.selection_set(obs_index)
            self.obs_list.see(obs_index)
        self.rgb_sets_only_var.set(True)
        self.refresh_product_list()
        self.product_list.selection_clear(0, "end")
        wanted = {id(result["rgb_set"][channel]) for channel in ("blue", "green", "red")}
        for index, row in enumerate(self.visible_product_results):
            if id(row) in wanted:
                self.product_list.selection_set(index)
                self.product_list.see(index)
        for channel in ("blue", "green", "red"):
            self.select_rgb_candidate_row(channel, result["rgb_set"][channel])
        self.red_path_var.set(str(result["channel_paths"]["red"]))
        self.green_path_var.set(str(result["channel_paths"]["green"]))
        self.blue_path_var.set(str(result["channel_paths"]["blue"]))
        self.preview_channel_thumbnails_async({
            "red": result["channel_paths"]["red"],
            "green": result["channel_paths"]["green"],
            "blue": result["channel_paths"]["blue"],
        }, compose_after=False)
        self.rgb_full_base_image = result["image"]
        self.rgb_full_base_float = result.get("rgb_float")
        self.rgb_base_image = result.get("base_image") or downsample_image_for_preview(self.rgb_full_base_image)
        self.rgb_base_float = result.get("base_float")
        self.rgb_headers = result["headers"]
        self.rgb_source_shapes = result["source_shapes"]
        self.rgb_resize_mode = result["resize_mode"]
        self.apply_image_tuning()
        self.generate_preset_previews()
        self.why_var.set(result.get("why", ""))
        preview_path = self.auto_save_preview_png()
        if result.get("high_quality_easy"):
            self.save_composite_outputs()
        self.download_progress_var.set(100)
        self.download_detail.set("Easy RGB complete.")
        self.notebook.select(self.compose_tab)
        size_text = f"{self.rgb_image.width} x {self.rgb_image.height}px"
        message = f"Easy RGB complete at {size_text}."
        if preview_path:
            message += f" Auto-saved {preview_path.name}."
        if result.get("high_quality_easy"):
            message += " Full PNG/TIFF/notes were saved automatically."
        self.stop_browser_activity(message)

    def on_tuning_changed(self, _value=None):
        if hasattr(self, "straighten_label"):
            self.straighten_label.configure(text=f"{self.straighten_angle_var.get():.1f} deg")
        if hasattr(self, "tuning_job") and self.tuning_job:
            try:
                self.after_cancel(self.tuning_job)
            except Exception:
                pass
        self.tuning_job = self.after(80, self.apply_image_tuning)

    def reset_straighten(self):
        self.straighten_angle_var.set(0.0)
        if hasattr(self, "straighten_label"):
            self.straighten_label.configure(text="0.0 deg")
        self.apply_image_tuning()

    def apply_image_tuning(self):
        if not hasattr(self, "rgb_base_image"):
            return
        self.rgb_image, self.rgb_float_image, self.presentation_cleanup_fills = self.render_tuned_image()
        self.update_rgb_preview()

    def render_tuned_image(self, base_image=None, base_float=None):
        if base_image is None:
            base_image = self.rgb_base_image
        if base_float is None:
            base_float = getattr(self, "rgb_base_float", None)
        if base_float is not None:
            arr = np.asarray(base_float, dtype=np.float32).copy()
            arr = arr - float(self.black_point_var.get()) / 255.0
            arr = arr + float(self.brightness_var.get()) / 255.0
            arr = (arr - 0.5) * float(self.contrast_var.get()) + 0.5
            arr[:, :, 0] *= float(self.red_balance_var.get())
            arr[:, :, 1] *= float(self.green_balance_var.get())
            arr[:, :, 2] *= float(self.blue_balance_var.get())
            gray = arr.mean(axis=2, keepdims=True)
            arr = gray + (arr - gray) * float(self.saturation_var.get())
            float_image = np.clip(arr, 0, 1).astype(np.float32)
            image = Image.fromarray(float_rgb_to_uint8(float_image), mode="RGB")
        else:
            arr = np.asarray(base_image, dtype=np.float32)
            arr = arr - float(self.black_point_var.get())
            arr = arr + float(self.brightness_var.get())
            arr = (arr - 127.5) * float(self.contrast_var.get()) + 127.5
            arr[:, :, 0] *= float(self.red_balance_var.get())
            arr[:, :, 1] *= float(self.green_balance_var.get())
            arr[:, :, 2] *= float(self.blue_balance_var.get())
            gray = arr.mean(axis=2, keepdims=True)
            arr = gray + (arr - gray) * float(self.saturation_var.get())
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            float_image = None
            image = Image.fromarray(arr, mode="RGB")
        fills = 0
        if getattr(self, "presentation_cleanup_var", None) is not None and self.presentation_cleanup_var.get():
            image, fills = fill_internal_black_gaps(image)
        image = presentation_transform(
            image,
            angle=self.straighten_angle_var.get() if hasattr(self, "straighten_angle_var") else 0.0,
            auto_crop=self.auto_crop_presentation_var.get() if hasattr(self, "auto_crop_presentation_var") else True,
        )
        return image, float_image, fills

    def update_rgb_preview(self):
        if self.view_tuned_var.get() and hasattr(self, "rgb_image"):
            image = self.rgb_image
        elif hasattr(self, "rgb_base_image"):
            image = self.rgb_base_image
        else:
            return
        self.show_image_on_canvas(self.rgb_canvas, image, "rgb_photo", zoom=float(self.preview_zoom_var.get()))

    def generate_preset_previews(self):
        if not hasattr(self, "preset_preview_canvases") or not hasattr(self, "rgb_base_image"):
            return
        for name, canvas in self.preset_preview_canvases.items():
            image = self.render_preset_preview(name)
            if image is None:
                continue
            self.show_image_on_canvas(canvas, image, f"preset_{name.replace(' ', '_').lower()}_photo")

    def render_preset_preview(self, name):
        values = self.preset_values(name)
        if not values:
            return None
        black, brightness, contrast, saturation, red_balance, green_balance, blue_balance = values
        if getattr(self, "rgb_base_float", None) is not None:
            preview_float = downsample_float_rgb_for_preview(self.rgb_base_float, RGB_PRESET_PREVIEW_MAX_PIXELS)
            arr = np.asarray(preview_float, dtype=np.float32).copy()
            arr = arr - black / 255.0
            arr = arr + brightness / 255.0
            arr = (arr - 0.5) * contrast + 0.5
            arr[:, :, 0] *= red_balance
            arr[:, :, 1] *= green_balance
            arr[:, :, 2] *= blue_balance
            gray = arr.mean(axis=2, keepdims=True)
            arr = gray + (arr - gray) * saturation
            return Image.fromarray(float_rgb_to_uint8(np.clip(arr, 0, 1)), mode="RGB")
        preview_image = downsample_image_for_preview(self.rgb_base_image, RGB_PRESET_PREVIEW_MAX_PIXELS)
        arr = np.asarray(preview_image, dtype=np.float32)
        arr = arr - black
        arr = arr + brightness
        arr = (arr - 127.5) * contrast + 127.5
        arr[:, :, 0] *= red_balance
        arr[:, :, 1] *= green_balance
        arr[:, :, 2] *= blue_balance
        gray = arr.mean(axis=2, keepdims=True)
        arr = gray + (arr - gray) * saturation
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")

    def apply_preset_preview(self, name):
        self.apply_processing_preset(name)
        self.generate_preset_previews()

    def preset_values(self, name):
        presets = {
            "Natural": (0, 0, 1.0, 1.0, 1.0, 1.0, 1.0),
            "High Contrast": (12, 8, 1.45, 1.2, 1.0, 1.0, 1.0),
            "Nebula": (10, 10, 1.25, 1.55, 1.12, 1.0, 1.08),
            "Blue/Pink Nebula": (35, -18, 1.45, 1.45, 0.95, 1.04, 1.28),
            "Galaxy": (8, 4, 1.2, 1.15, 1.08, 1.0, 0.95),
            "Soft Stretch": (4, 12, 0.9, 1.25, 1.0, 1.0, 1.04),
        }
        return presets.get(name)

    def apply_processing_preset(self, name, update_status=True):
        values = self.preset_values(name)
        if not values:
            return
        variables = (
            self.black_point_var,
            self.brightness_var,
            self.contrast_var,
            self.saturation_var,
            self.red_balance_var,
            self.green_balance_var,
            self.blue_balance_var,
        )
        for variable, value in zip(variables, values):
            variable.set(value)
        if name == "Blue/Pink Nebula" and hasattr(self, "channel_stretch_vars"):
            channel_settings = {
                "red": {"low": 0.35, "high": 99.85, "gamma": 0.95, "asinh": 14.0},
                "green": {"low": 0.20, "high": 99.80, "gamma": 1.0, "asinh": 12.0},
                "blue": {"low": 0.12, "high": 99.90, "gamma": 1.05, "asinh": 16.0},
            }
            for channel, settings in channel_settings.items():
                if channel not in self.channel_stretch_vars:
                    continue
                for key, value in settings.items():
                    self.channel_stretch_vars[channel][key].set(value)
            self.compose_stretch_var.set("asinh")
            self.save_quality_settings()
        self.apply_image_tuning()
        if update_status:
            if name == "Blue/Pink Nebula":
                self.compose_status.set("Applied Blue/Pink Nebula preset. Compose RGB again to include its advanced stretch settings.")
            else:
                self.compose_status.set(f"Applied {name} preset.")
