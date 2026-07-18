from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

import numpy as np
from PIL import Image

from .hydrogen_processing import HYDROGEN_PRESETS, process_hydrogen_rgb
from .image_processing import float_rgb_to_uint8, float_rgb_to_uint16
from .paths import OUTPUT_DIR

try:
    import tifffile
except Exception:
    tifffile = None


class HydrogenWorkflowMixin:
    def build_hydrogen_tab(self):
        content = ttk.Frame(self.hydrogen_tab)
        content.pack(fill="both", expand=True)
        control_outer = ttk.Frame(content, width=330)
        control_outer.pack(side="left", fill="y", padx=(0, 10))
        control_outer.pack_propagate(False)
        control_canvas = tk.Canvas(control_outer, bg="#f3f3f3", highlightthickness=0, width=305)
        control_scrollbar = ttk.Scrollbar(control_outer, orient="vertical", command=control_canvas.yview)
        controls = ttk.Frame(control_canvas)
        control_window = control_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda _event: control_canvas.configure(scrollregion=control_canvas.bbox("all")))
        control_canvas.bind("<Configure>", lambda event: control_canvas.itemconfigure(control_window, width=event.width))
        control_canvas.configure(yscrollcommand=control_scrollbar.set)
        control_canvas.pack(side="left", fill="both", expand=True)
        control_scrollbar.pack(side="right", fill="y")
        ttk.Label(controls, text="Hydrogen / H-II Enhancement", style="Title.TLabel", wraplength=290).pack(anchor="w")
        ttk.Label(
            controls,
            text="Visually emphasizes compact hydrogen-rich structures in a finished RGB image. This is an enhancement proxy, not calibrated H-alpha data.",
            wraplength=290,
        ).pack(anchor="w", pady=(4, 10))
        buttons = ttk.Frame(controls)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Use Final Composite", command=self.hydrogen_use_composite, style="Accent.TButton").pack(side="left")
        ttk.Button(buttons, text="Open Image", command=self.hydrogen_open_image).pack(side="left", padx=(6, 0))

        self.hydrogen_preset_var = tk.StringVar(value="Vibrant Magenta/Pink")
        self.hydrogen_glow_var = tk.DoubleVar(value=1.5)
        self.hydrogen_kernel_var = tk.IntVar(value=15)
        self.hydrogen_stretch_var = tk.DoubleVar(value=15.0)
        self.hydrogen_black_var = tk.DoubleVar(value=0.0)
        self.hydrogen_sky_var = tk.DoubleVar(value=2.0)
        self.hydrogen_tolerance_var = tk.IntVar(value=10)
        self.hydrogen_red_scale_var = tk.DoubleVar(value=1.0)
        self.hydrogen_green_scale_var = tk.DoubleVar(value=1.0)
        self.hydrogen_blue_scale_var = tk.DoubleVar(value=1.0)
        self.hydrogen_mask_background_var = tk.BooleanVar(value=True)
        self.hydrogen_smooth_var = tk.BooleanVar(value=True)
        self.hydrogen_view_var = tk.StringVar(value="Side by Side")

        ttk.Label(controls, text="Color preset", style="Section.TLabel").pack(anchor="w", pady=(14, 3))
        preset = ttk.Combobox(controls, textvariable=self.hydrogen_preset_var, values=list(HYDROGEN_PRESETS), state="readonly")
        preset.pack(fill="x")
        preset.bind("<<ComboboxSelected>>", self.hydrogen_update_preview)
        self._hydrogen_scale(controls, "Glow strength", self.hydrogen_glow_var, 0, 5)
        self._hydrogen_scale(controls, "H-II region size", self.hydrogen_kernel_var, 5, 31)
        self._hydrogen_scale(controls, "Arcsinh stretch", self.hydrogen_stretch_var, 1, 50)
        self._hydrogen_scale(controls, "Black point", self.hydrogen_black_var, 0, 0.2)
        self._hydrogen_scale(controls, "Sky percentile", self.hydrogen_sky_var, 0, 10)
        self._hydrogen_scale(controls, "Border tolerance", self.hydrogen_tolerance_var, 0, 100)
        self._hydrogen_scale(controls, "Red scale", self.hydrogen_red_scale_var, 0.5, 2.0)
        self._hydrogen_scale(controls, "Green scale", self.hydrogen_green_scale_var, 0.5, 2.0)
        self._hydrogen_scale(controls, "Blue scale", self.hydrogen_blue_scale_var, 0.5, 2.0)
        ttk.Checkbutton(controls, text="Mask matching border color", variable=self.hydrogen_mask_background_var, command=self.hydrogen_update_preview).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(controls, text="Gentle final smoothing", variable=self.hydrogen_smooth_var, command=self.hydrogen_update_preview).pack(anchor="w")
        ttk.Button(controls, text="Use Top-Left as Background", command=self.hydrogen_use_corner_background).pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Save Enhanced PNG + TIFF", command=self.hydrogen_save_outputs).pack(fill="x", pady=(8, 0))
        self.hydrogen_status_var = tk.StringVar(value="Use the final composite or open an RGB image.")
        ttk.Label(controls, textvariable=self.hydrogen_status_var, wraplength=290).pack(anchor="w", pady=(10, 0))

        viewer = ttk.Frame(content)
        viewer.pack(side="right", fill="both", expand=True)
        view_controls = ttk.Frame(viewer)
        view_controls.pack(fill="x", pady=(0, 6))
        ttk.Label(view_controls, text="View").pack(side="left")
        view = ttk.Combobox(view_controls, textvariable=self.hydrogen_view_var, values=["Side by Side", "Original", "H-II Mask", "Enhanced"], state="readonly", width=16)
        view.pack(side="left", padx=(6, 0))
        view.bind("<<ComboboxSelected>>", self.hydrogen_update_preview)
        self.hydrogen_canvas = tk.Canvas(viewer, bg="#111318", highlightthickness=0)
        self.hydrogen_canvas.pack(fill="both", expand=True)
        self.hydrogen_canvas.bind("<Configure>", self.hydrogen_update_preview)
        self.hydrogen_canvas.bind("<Button-1>", self.hydrogen_select_background)

    def _hydrogen_scale(self, parent, label, variable, start, stop):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(7, 0))
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Scale(frame, variable=variable, from_=start, to=stop, command=self.hydrogen_update_preview).pack(fill="x")

    def hydrogen_use_composite(self):
        if not hasattr(self, "rgb_full_base_image"):
            messagebox.showinfo("Hydrogen Enhance", "Compose an RGB image first.")
            return
        image, float_image, _fills = self.render_tuned_image(
            base_image=self.rgb_full_base_image,
            base_float=getattr(self, "rgb_full_base_float", None),
        )
        if float_image is not None and float_image.shape[:2] == (image.height, image.width):
            self.hydrogen_full_rgb = np.asarray(float_image, dtype=np.float32).copy()
        else:
            self.hydrogen_full_rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        self.hydrogen_source_name = "final_composite"
        self.hydrogen_background_color = self.hydrogen_full_rgb[0, 0].copy()
        self.hydrogen_prepare_preview()

    def hydrogen_open_image(self):
        path = filedialog.askopenfilename(filetypes=[("RGB images", "*.png *.jpg *.jpeg *.tif *.tiff"), ("All files", "*.*")])
        if not path:
            return
        try:
            suffix = Path(path).suffix.lower()
            if suffix in (".tif", ".tiff") and tifffile is not None:
                data = np.asarray(tifffile.imread(path))
                if data.ndim != 3 or data.shape[2] < 3:
                    raise ValueError("TIFF is not an RGB image.")
                data = data[:, :, :3].astype(np.float32)
                scale = 65535.0 if data.max() > 255 else 255.0
                self.hydrogen_full_rgb = np.clip(data / scale, 0, 1)
            else:
                image = Image.open(path).convert("RGB")
                self.hydrogen_full_rgb = np.asarray(image, dtype=np.float32) / 255.0
        except Exception as exc:
            messagebox.showerror("Hydrogen Enhance", f"Could not open image: {exc}")
            return
        self.hydrogen_source_name = Path(path).stem
        self.hydrogen_background_color = self.hydrogen_full_rgb[0, 0].copy()
        self.hydrogen_prepare_preview()

    def hydrogen_prepare_preview(self):
        image = Image.fromarray(float_rgb_to_uint8(self.hydrogen_full_rgb), mode="RGB")
        image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
        self.hydrogen_preview_rgb = np.asarray(image, dtype=np.float32) / 255.0
        self.hydrogen_update_preview()

    def hydrogen_use_corner_background(self):
        if not hasattr(self, "hydrogen_preview_rgb"):
            return
        self.hydrogen_background_color = self.hydrogen_preview_rgb[0, 0].copy()
        self.hydrogen_update_preview()

    def hydrogen_settings(self):
        kernel = int(round(self.hydrogen_kernel_var.get()))
        if kernel % 2 == 0:
            kernel -= 1
        return {
            "background_color": getattr(self, "hydrogen_background_color", None),
            "mask_background": self.hydrogen_mask_background_var.get(),
            "tolerance": self.hydrogen_tolerance_var.get(),
            "channel_scales": (
                self.hydrogen_red_scale_var.get(),
                self.hydrogen_green_scale_var.get(),
                self.hydrogen_blue_scale_var.get(),
            ),
            "stretch_factor": self.hydrogen_stretch_var.get(),
            "black_point": self.hydrogen_black_var.get(),
            "sky_percentile": self.hydrogen_sky_var.get(),
            "preset": self.hydrogen_preset_var.get(),
            "glow_strength": self.hydrogen_glow_var.get(),
            "kernel_size": max(5, kernel),
            "smooth": self.hydrogen_smooth_var.get(),
        }

    def hydrogen_update_preview(self, _event=None):
        if not hasattr(self, "hydrogen_preview_rgb"):
            return
        try:
            enhanced, mask = process_hydrogen_rgb(self.hydrogen_preview_rgb, **self.hydrogen_settings())
        except Exception as exc:
            self.hydrogen_status_var.set(f"Preview failed: {exc}")
            return
        original = Image.fromarray(float_rgb_to_uint8(self.hydrogen_preview_rgb), mode="RGB")
        enhanced_image = Image.fromarray(float_rgb_to_uint8(enhanced), mode="RGB")
        mask_image = Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8), mode="L").convert("RGB")
        view = self.hydrogen_view_var.get()
        if view == "Original":
            display = original
        elif view == "H-II Mask":
            display = mask_image
        elif view == "Enhanced":
            display = enhanced_image
        else:
            height = max(original.height, enhanced_image.height)
            display = Image.new("RGB", (original.width + enhanced_image.width, height), "black")
            display.paste(original, (0, 0))
            display.paste(enhanced_image, (original.width, 0))
        self.show_image_on_canvas(self.hydrogen_canvas, display, "hydrogen_photo")
        self.hydrogen_display_image_size = display.size
        self.hydrogen_status_var.set(f"Preview ready: {self.hydrogen_source_name}. Mask peak {mask.max() * 100:.1f}%.")

    def hydrogen_select_background(self, event):
        if not hasattr(self, "hydrogen_preview_rgb") or not hasattr(self, "hydrogen_display_image_size"):
            return
        canvas_width = max(320, self.hydrogen_canvas.winfo_width())
        canvas_height = max(240, self.hydrogen_canvas.winfo_height())
        display_width, display_height = self.hydrogen_display_image_size
        scale = min(1.0, canvas_width / display_width, canvas_height / display_height)
        shown_width = display_width * scale
        shown_height = display_height * scale
        x = (event.x - (canvas_width - shown_width) / 2.0) / scale
        y = (event.y - (canvas_height - shown_height) / 2.0) / scale
        original_width = self.hydrogen_preview_rgb.shape[1]
        original_height = self.hydrogen_preview_rgb.shape[0]
        if self.hydrogen_view_var.get() == "Side by Side" and x >= original_width:
            x -= original_width
        if 0 <= x < original_width and 0 <= y < original_height:
            self.hydrogen_background_color = self.hydrogen_preview_rgb[int(y), int(x)].copy()
            self.hydrogen_update_preview()
            self.hydrogen_status_var.set(f"Selected background color at preview pixel {int(x)}, {int(y)}.")

    def hydrogen_save_outputs(self):
        if not hasattr(self, "hydrogen_full_rgb"):
            messagebox.showinfo("Hydrogen Enhance", "Load or compose an image first.")
            return
        try:
            enhanced, mask = process_hydrogen_rgb(self.hydrogen_full_rgb, **self.hydrogen_settings())
            OUTPUT_DIR.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = OUTPUT_DIR / f"{self.hydrogen_source_name}_hydrogen_enhanced_{stamp}"
            png_path = base.with_suffix(".png")
            tiff_path = base.with_suffix(".tiff")
            mask_path = base.with_name(base.name + "_mask.png")
            Image.fromarray(float_rgb_to_uint8(enhanced), mode="RGB").save(png_path)
            if tifffile is not None:
                tifffile.imwrite(str(tiff_path), float_rgb_to_uint16(enhanced), photometric="rgb")
            else:
                Image.fromarray(float_rgb_to_uint8(enhanced), mode="RGB").save(tiff_path)
            Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8), mode="L").save(mask_path)
            self.last_output_path = png_path
            self.hydrogen_status_var.set(f"Saved {png_path.name}, 16-bit TIFF, and mask.")
        except Exception as exc:
            messagebox.showerror("Hydrogen Enhance", f"Save failed: {exc}")
