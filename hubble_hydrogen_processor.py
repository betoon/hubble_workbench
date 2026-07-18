import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk
import os

class HubbleProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Hubble Hydrogen-Alpha Image Processor Pro")
        self.root.geometry("1200x800")
        
        # Configure dark mode theme colors
        self.bg_dark = "#121216"
        self.bg_panel = "#1e1e24"
        self.bg_control = "#2d2d34"
        self.fg_white = "#ffffff"
        self.fg_gray = "#aaaaaa"
        self.accent_color = "#e94560"
        
        self.root.configure(bg=self.bg_dark)
        
        # Initialize variables
        self.full_img = None      # Full-res BGR image
        self.preview_img = None   # Scaled BGR image for real-time processing
        self.detected_bg = np.array([184, 44, 56], dtype=np.uint8) # default pink background color
        
        # Hydrogen color presets mapping to (B, G, R)
        self.hydrogen_presets = {
            "Vibrant Magenta/Pink": (180, 50, 255),
            "Natural H-Alpha Red": (0, 0, 255),
            "Hubble Palette Green": (0, 255, 0),
            "OIII Cyan/Blue": (255, 255, 0),
            "Electric Purple": (255, 0, 180)
        }
        
        # Set up GUI layouts
        self.setup_styles()
        self.create_widgets()
        
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # Custom styles for ttk elements in dark theme
        style.configure("TFrame", background=self.bg_dark)
        style.configure("Panel.TFrame", background=self.bg_panel)
        style.configure("Control.TFrame", background=self.bg_control)
        style.configure("TLabel", background=self.bg_panel, foreground=self.fg_white, font=("Arial", 9))
        style.configure("Title.TLabel", background=self.bg_panel, foreground=self.accent_color, font=("Arial", 12, "bold"))
        style.configure("Section.TLabel", background=self.bg_panel, foreground=self.accent_color, font=("Arial", 10, "bold"))
        
        style.configure("TButton", background=self.accent_color, foreground=self.fg_white, borderwidth=0, font=("Arial", 10, "bold"))
        style.map("TButton", background=[("active", "#d32f2f")])
        
        # Tab notebook styling
        style.configure("TNotebook", background=self.bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.bg_panel, foreground=self.fg_gray, font=("Arial", 10))
        style.map("TNotebook.Tab", background=[("selected", self.accent_color)], foreground=[("selected", self.fg_white)])

    def create_widgets(self):
        # Main Layout: Left control panel, Right image tabs
        main_container = ttk.Frame(self.root, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left Panel (Width ~ 380) with a canvas + scrollbar to handle many controls
        left_outer = ttk.Frame(main_container, style="Panel.TFrame", width=380)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_outer.pack_propagate(False)
        
        # Scrollable area
        canvas = tk.Canvas(left_outer, bg=self.bg_panel, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_outer, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="Panel.TFrame")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=360)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel scroll
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Title & Browse
        title_label = ttk.Label(scrollable_frame, text="Hubble Image Processor Pro", style="Title.TLabel")
        title_label.pack(anchor=tk.W, pady=(5, 10))
        
        self.browse_btn = ttk.Button(scrollable_frame, text="Browse Hubble Image", command=self.load_image)
        self.browse_btn.pack(fill=tk.X, pady=(0, 15))
        
        # View Settings Section
        self.create_section_header(scrollable_frame, "View & File Settings")
        
        self.sxs_var = tk.BooleanVar(value=True)
        self.chk_sxs = tk.Checkbutton(scrollable_frame, text="Side-by-Side Comparison", variable=self.sxs_var, 
                                      bg=self.bg_panel, fg=self.fg_white, selectcolor=self.bg_dark,
                                      activebackground=self.bg_panel, activeforeground=self.fg_white,
                                      font=("Arial", 9), command=self.toggle_view_mode)
        self.chk_sxs.pack(anchor=tk.W, pady=(0, 10))
        
        # Background & Masking Section
        self.create_section_header(scrollable_frame, "Background & Masking")
        
        self.mask_bg_var = tk.BooleanVar(value=True)
        self.chk_mask_bg = tk.Checkbutton(scrollable_frame, text="Enable Borders Mask", variable=self.mask_bg_var, 
                                          bg=self.bg_panel, fg=self.fg_white, selectcolor=self.bg_dark,
                                          activebackground=self.bg_panel, activeforeground=self.fg_white,
                                          font=("Arial", 9), command=self.update_preview)
        self.chk_mask_bg.pack(anchor=tk.W, pady=(0, 5))
        
        self.info_lbl = ttk.Label(scrollable_frame, text="💡 Tip: Click original image to select bg color.", font=("Arial", 8, "italic"), foreground=self.fg_gray)
        self.info_lbl.pack(anchor=tk.W, pady=(0, 10))
        
        self.tol_var = tk.IntVar(value=10)
        self.create_slider_control(scrollable_frame, "Borders Mask Tolerance", self.tol_var, 0, 100, self.update_preview)
        
        # Color Balance Section
        self.create_section_header(scrollable_frame, "Galactic Color Balance")
        
        self.r_scale_var = tk.DoubleVar(value=1.0)
        self.create_slider_control(scrollable_frame, "Red Channel Scale", self.r_scale_var, 0.5, 2.0, self.update_preview, resolution=0.05)
        
        self.g_scale_var = tk.DoubleVar(value=1.0)
        self.create_slider_control(scrollable_frame, "Green Channel Scale", self.g_scale_var, 0.5, 2.0, self.update_preview, resolution=0.05)
        
        self.b_scale_var = tk.DoubleVar(value=1.0)
        self.create_slider_control(scrollable_frame, "Blue Channel Scale", self.b_scale_var, 0.5, 2.0, self.update_preview, resolution=0.05)
        
        # Stretching & Sky Level Section
        self.create_section_header(scrollable_frame, "Exposure & Stretching")
        
        self.stretch_var = tk.DoubleVar(value=15.0)
        self.create_slider_control(scrollable_frame, "Arcsinh Stretch Factor", self.stretch_var, 1.0, 50.0, self.update_preview, resolution=0.5)
        
        self.black_var = tk.DoubleVar(value=0.0)
        self.create_slider_control(scrollable_frame, "Black Point Cutoff", self.black_var, 0.0, 0.2, self.update_preview, resolution=0.005)
        
        self.sky_var = tk.DoubleVar(value=2.0)
        self.create_slider_control(scrollable_frame, "Sky Background Percentile", self.sky_var, 0.0, 10.0, self.update_preview, resolution=0.1)
        
        # Hydrogen-Alpha Isolation Section
        self.create_section_header(scrollable_frame, "Hydrogen (H-II) Isolation")
        
        preset_frame = ttk.Frame(scrollable_frame, style="Panel.TFrame")
        preset_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(preset_frame, text="Hydrogen Gas Color Preset:").pack(anchor=tk.W, pady=(0, 2))
        self.preset_var = tk.StringVar(value="Vibrant Magenta/Pink")
        self.combo_preset = ttk.Combobox(preset_frame, textvariable=self.preset_var, values=list(self.hydrogen_presets.keys()), state="readonly")
        self.combo_preset.pack(fill=tk.X)
        self.combo_preset.bind("<<ComboboxSelected>>", lambda e: self.update_preview())
        
        self.glow_var = tk.DoubleVar(value=1.5)
        self.create_slider_control(scrollable_frame, "Hydrogen Glow Strength", self.glow_var, 0.0, 5.0, self.update_preview, resolution=0.1)
        
        self.kernel_var = tk.IntVar(value=15)
        self.create_slider_control(scrollable_frame, "H-II Region Size (Kernel)", self.kernel_var, 5, 31, self.update_preview, is_odd=True)
        
        # Save Action Button
        ttk.Separator(scrollable_frame, orient="horizontal").pack(fill=tk.X, pady=(10, 15))
        self.save_btn = ttk.Button(scrollable_frame, text="Save Processed Image", command=self.save_full_image)
        self.save_btn.pack(fill=tk.X, pady=(0, 15))
        self.save_btn.state(["disabled"])
        
        # Right Panel (Tabbed Notebook / Side-by-Side comparison area)
        self.right_panel = ttk.Frame(main_container)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 1. Single View notebook
        self.notebook = ttk.Notebook(self.right_panel)
        
        self.tab_orig = ttk.Frame(self.notebook)
        self.tab_h_alpha = ttk.Frame(self.notebook)
        self.tab_enhanced = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_orig, text="  Original Image  ")
        self.notebook.add(self.tab_h_alpha, text="  H-Alpha (Hydrogen) Mask  ")
        self.notebook.add(self.tab_enhanced, text="  Hydrogen-Enhanced Composite  ")
        
        self.label_orig = tk.Label(self.tab_orig, bg=self.bg_dark, cursor="crosshair")
        self.label_orig.pack(fill=tk.BOTH, expand=True)
        self.label_orig.bind("<Button-1>", self.on_image_click)
        
        self.label_h_alpha = tk.Label(self.tab_h_alpha, bg=self.bg_dark)
        self.label_h_alpha.pack(fill=tk.BOTH, expand=True)
        
        self.label_enhanced = tk.Label(self.tab_enhanced, bg=self.bg_dark)
        self.label_enhanced.pack(fill=tk.BOTH, expand=True)
        
        # 2. Side-by-side View frame
        self.sxs_frame = ttk.Frame(self.right_panel)
        self.sxs_orig_lbl = tk.Label(self.sxs_frame, bg=self.bg_dark, cursor="crosshair")
        self.sxs_orig_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.sxs_orig_lbl.bind("<Button-1>", self.on_image_click)
        
        self.sxs_enh_lbl = tk.Label(self.sxs_frame, bg=self.bg_dark)
        self.sxs_enh_lbl.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Initialize default view: Side-by-Side is enabled by default
        self.toggle_view_mode()
        
        # Status Bar
        self.status_var = tk.StringVar(value="Status: Ready. Load a Hubble image to begin.")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, bg=self.bg_dark, fg=self.fg_gray, anchor=tk.W, font=("Arial", 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=2)

    def create_section_header(self, parent, text):
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill=tk.X, pady=(10, 5))
        
        lbl = ttk.Label(frame, text=text, style="Section.TLabel")
        lbl.pack(side=tk.LEFT)
        
        sep = ttk.Separator(frame, orient="horizontal")
        sep.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), pady=8)

    def create_slider_control(self, parent, label_text, var, from_val, to_val, command_cb, resolution=1, is_odd=False):
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill=tk.X, pady=(0, 8))
        
        header_frame = ttk.Frame(frame, style="Panel.TFrame")
        header_frame.pack(fill=tk.X)
        
        lbl = ttk.Label(header_frame, text=label_text)
        lbl.pack(side=tk.LEFT)
        
        val_lbl = ttk.Label(header_frame, text=f"{var.get():.2f}" if isinstance(resolution, float) else f"{var.get()}")
        val_lbl.pack(side=tk.RIGHT)
        
        def on_slider_move(val):
            float_val = float(val)
            if is_odd:
                int_val = int(float_val)
                if int_val % 2 == 0:
                    int_val = max(5, int_val - 1)
                var.set(int_val)
                val_lbl.configure(text=f"{int_val}")
            else:
                if isinstance(resolution, float):
                    var.set(round(float_val, 4))
                    val_lbl.configure(text=f"{var.get():.2f}")
                else:
                    var.set(int(float_val))
                    val_lbl.configure(text=f"{var.get()}")
            command_cb()
            
        slider = tk.Scale(frame, from_=from_val, to=to_val, orient=tk.HORIZONTAL, variable=var,
                          showvalue=0, bg=self.bg_panel, fg=self.fg_white, highlightthickness=0,
                          troughcolor=self.bg_dark, activebackground=self.accent_color,
                          resolution=resolution, command=on_slider_move)
        slider.pack(fill=tk.X, pady=(2, 0))

    def toggle_view_mode(self):
        if self.sxs_var.get():
            self.notebook.pack_forget()
            self.sxs_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.sxs_frame.pack_forget()
            self.notebook.pack(fill=tk.BOTH, expand=True)
        self.update_preview()

    def on_image_click(self, event):
        if self.preview_img is None:
            return
            
        # Get click coordinates on original label widget
        click_x = event.x
        click_y = event.y
        
        # Get label dimensions
        label = event.widget
        label_w = label.winfo_width()
        label_h = label.winfo_height()
        
        # Calculate image aspect ratio and true display size (since label scales image)
        img_h, img_w = self.preview_img.shape[:2]
        
        scale = min(label_w / img_w, label_h / img_h)
        display_w = int(img_w * scale)
        display_h = int(img_h * scale)
        
        # Calculate margins
        margin_x = (label_w - display_w) // 2
        margin_y = (label_h - display_h) // 2
        
        # Adjust click coordinates relative to the image
        img_click_x = click_x - margin_x
        img_click_y = click_y - margin_y
        
        # If click is within the displayed image bounds, read pixel
        if 0 <= img_click_x < display_w and 0 <= img_click_y < display_h:
            # Map back to preview image coordinates
            preview_x = int(img_click_x / scale)
            preview_y = int(img_click_y / scale)
            
            # Read BGR color
            self.detected_bg = self.preview_img[preview_y, preview_x].copy()
            self.status_var.set(f"Selected background BGR color: {self.detected_bg} at ({preview_x}, {preview_y}).")
            self.update_preview()

    def load_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.tif *.tiff *.fit *.fits"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        self.status_var.set(f"Status: Loading {os.path.basename(file_path)}...")
        self.root.update_idletasks()
        
        img = cv2.imread(file_path)
        if img is None:
            messagebox.showerror("Error", f"Failed to load image: {file_path}")
            self.status_var.set("Status: Error loading image.")
            return
            
        self.full_img = img
        self.detected_bg = img[0, 0].copy() # auto-detect from pixel (0,0)
        
        # Scale for fast real-time preview
        h, w = img.shape[:2]
        max_dim = 600
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            preview_w = int(w * scale)
            preview_h = int(h * scale)
            self.preview_img = cv2.resize(img, (preview_w, preview_h))
        else:
            self.preview_img = img.copy()
            
        self.save_btn.state(["!disabled"])
        self.update_preview()
        self.status_var.set(f"Status: Loaded {os.path.basename(file_path)} successfully.")

    def process_image_data(self, bgr_img):
        # Extract variables
        mask_bg = self.mask_bg_var.get()
        tol = self.tol_var.get()
        r_scale = self.r_scale_var.get()
        g_scale = self.g_scale_var.get()
        b_scale = self.b_scale_var.get()
        stretch_factor = self.stretch_var.get()
        black_point = self.black_var.get()
        sky_p = self.sky_var.get()
        glow_factor = self.glow_var.get()
        kernel_size = self.kernel_var.get()
        
        if kernel_size % 2 == 0:
            kernel_size = max(5, kernel_size - 1)
            
        h, w = bgr_img.shape[:2]
        bg_mask = np.zeros((h, w), dtype=bool)
        if mask_bg:
            # Mask color ranges
            diff = np.abs(bgr_img.astype(np.int32) - self.detected_bg)
            bg_mask = np.all(diff <= tol, axis=-1)
            
        b, g, r = cv2.split(bgr_img)
        
        b[bg_mask] = 0
        g[bg_mask] = 0
        r[bg_mask] = 0
        
        # 1. Color Balance adjustment
        b_bal = np.clip(b.astype(np.float32) * b_scale, 0, 255)
        g_bal = np.clip(g.astype(np.float32) * g_scale, 0, 255)
        r_bal = np.clip(r.astype(np.float32) * r_scale, 0, 255)
        
        # 2. Subtract sky background offset
        def subtract_sky(ch, mask):
            non_bg = ch[~mask]
            if len(non_bg) == 0:
                return ch
            bg_offset = np.percentile(non_bg, sky_p)
            return np.clip(ch - bg_offset, 0, 255)
            
        b_sub = subtract_sky(b_bal, bg_mask)
        g_sub = subtract_sky(g_bal, bg_mask)
        r_sub = subtract_sky(r_bal, bg_mask)
        
        # 3. Arcsinh Stretch
        def arcsinh_stretch(ch):
            ch_norm = ch / 255.0
            ch_shifted = np.clip(ch_norm - black_point, 0.0, 1.0)
            stretched = np.arcsinh(stretch_factor * ch_shifted) / np.arcsinh(stretch_factor)
            return np.clip(stretched * 255.0, 0, 255).astype(np.uint8)
            
        b_stretched = arcsinh_stretch(b_sub)
        g_stretched = arcsinh_stretch(g_sub)
        r_stretched = arcsinh_stretch(r_sub)
        
        b_stretched[bg_mask] = 0
        g_stretched[bg_mask] = 0
        r_stretched[bg_mask] = 0
        
        cc_rgb = cv2.merge([b_stretched, g_stretched, r_stretched])
        
        # 4. H-alpha Proxy Isolation
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        b_tophat = cv2.morphologyEx(b_stretched, cv2.MORPH_TOPHAT, kernel)
        r_tophat = cv2.morphologyEx(r_stretched, cv2.MORPH_TOPHAT, kernel)
        
        h_alpha = cv2.bitwise_and(b_tophat, r_tophat)
        h_alpha = cv2.addWeighted(h_alpha, 0.7, b_tophat, 0.3, 0)
        h_alpha[bg_mask] = 0
        
        # 5. Blend Preset Hydrogen Color
        preset_name = self.preset_var.get()
        preset_b, preset_g, preset_r = self.hydrogen_presets.get(preset_name, (180, 50, 255))
        
        glow = cv2.GaussianBlur(h_alpha, (5, 5), 0)
        glow_factor_norm = glow_factor / 100.0
        
        enhanced = cc_rgb.copy().astype(np.float32)
        # B
        enhanced[:, :, 0] = np.clip(enhanced[:, :, 0] + glow_factor_norm * glow * preset_b, 0, 255)
        # G
        enhanced[:, :, 1] = np.clip(enhanced[:, :, 1] - glow_factor_norm * glow * (255 - preset_g) * 0.1, 0, 255) # suppress green relative to preset
        enhanced[:, :, 1] = np.clip(enhanced[:, :, 1] + glow_factor_norm * glow * preset_g * 0.5, 0, 255)
        # R
        enhanced[:, :, 2] = np.clip(enhanced[:, :, 2] + glow_factor_norm * glow * preset_r, 0, 255)
        
        enhanced = enhanced.astype(np.uint8)
        enhanced[bg_mask] = 0
        
        # Denoise/smooth galaxies slightly
        denoised = cv2.bilateralFilter(enhanced, d=5, sigmaColor=25, sigmaSpace=25)
        denoised[bg_mask] = 0
        
        return denoised, h_alpha

    def update_preview(self):
        if self.preview_img is None:
            return
            
        enhanced, h_alpha = self.process_image_data(self.preview_img)
        
        # Convert preview original and results to RGB for display
        orig_rgb = cv2.cvtColor(self.preview_img, cv2.COLOR_BGR2RGB)
        enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
        h_alpha_pil = Image.fromarray(h_alpha)
        
        # In Side-by-Side view, we resize images to fit the split view pane
        if self.sxs_var.get():
            # Get split view dimensions
            pane_w = self.sxs_frame.winfo_width() // 2 - 10
            pane_h = self.sxs_frame.winfo_height() - 10
            
            # Default fallback size if widget is not fully rendered yet
            if pane_w <= 0 or pane_h <= 0:
                pane_w, pane_h = 390, 580
                
            img_h, img_w = self.preview_img.shape[:2]
            scale = min(pane_w / img_w, pane_h / img_h)
            disp_w = int(img_w * scale)
            disp_h = int(img_h * scale)
            
            # Create Tkinter PhotoImages
            orig_pil = Image.fromarray(orig_rgb).resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            orig_tk = ImageTk.PhotoImage(orig_pil)
            self.sxs_orig_lbl.configure(image=orig_tk)
            self.sxs_orig_lbl.image = orig_tk
            
            enh_pil = Image.fromarray(enhanced_rgb).resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            enh_tk = ImageTk.PhotoImage(enh_pil)
            self.sxs_enh_lbl.configure(image=enh_tk)
            self.sxs_enh_lbl.image = enh_tk
        else:
            # Normal tabbed view
            orig_tk = ImageTk.PhotoImage(Image.fromarray(orig_rgb))
            self.label_orig.configure(image=orig_tk)
            self.label_orig.image = orig_tk
            
            h_alpha_tk = ImageTk.PhotoImage(h_alpha_pil)
            self.label_h_alpha.configure(image=h_alpha_tk)
            self.label_h_alpha.image = h_alpha_tk
            
            enhanced_tk = ImageTk.PhotoImage(Image.fromarray(enhanced_rgb))
            self.label_enhanced.configure(image=enhanced_tk)
            self.label_enhanced.image = enhanced_tk

    def save_full_image(self):
        if self.full_img is None:
            return
            
        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Files", "*.png"), ("JPEG Files", "*.jpg *.jpeg"), ("All Files", "*.*")]
        )
        if not save_path:
            return
            
        self.status_var.set("Status: Processing full-resolution image and saving...")
        self.root.update_idletasks()
        
        try:
            full_enhanced, _ = self.process_image_data(self.full_img)
            cv2.imwrite(save_path, full_enhanced)
            self.status_var.set(f"Status: Saved enhanced image to {os.path.basename(save_path)} successfully.")
            messagebox.showinfo("Success", f"Enhanced image saved successfully:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save image: {str(e)}")
            self.status_var.set("Status: Error saving image.")

if __name__ == "__main__":
    root = tk.Tk()
    app = HubbleProcessorApp(root)
    # Trigger an initial configure bind event to render images nicely once window opens
    root.bind("<Configure>", lambda event: app.update_preview() if event.widget == root else None)
    root.mainloop()
