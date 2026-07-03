import json
import math
import threading
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
import atexit
import platform
from functools import wraps
import html
import io
import shutil
import subprocess
import tempfile
import traceback
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageTk

# Disable the decompression bomb protection entirely

Image.MAX_IMAGE_PIXELS = None

try:
    import tifffile
except Exception:
    tifffile = None


from hubble_workbench_app.paths import (
    APP_DIR,
    DOWNLOAD_DIR,
    OUTPUT_DIR,
    NOTES_DIR,
    SETTINGS_PATH,
    MESSIER_LIST_PATH,
    RGB_WORKING_PREVIEW_MAX_PIXELS,
    RGB_PRESET_PREVIEW_MAX_PIXELS,
    CHANNEL_THUMBNAIL_MAX_PIXELS,
    ENHANCED_PRODUCT_TOKENS,
    DEBUG_LOG_PATH,
    LOG_DIR,
    SEARCH_LOG_DIR,
    PRODUCT_LOG_DIR,
    DOWNLOAD_LOG_DIR,
    COMPOSE_LOG_DIR,
    TIMING_LOG_DIR,
    DEVELOPER_LOG_DIRS,
)
from hubble_workbench_app.settings import load_settings, save_settings
from hubble_workbench_app.image_processing import (
    normalize_image,
    normalize_float_channel,
    resize_to_match,
    resize_float_to_match,
    downsample_float_rgb_for_preview,
    downsample_image_for_preview,
    downsample_array_for_preview,
    float_rgb_to_uint8,
    float_rgb_to_uint16,
    patch_sample_color,
    blended_gap_image,
    crop_black_border,
    presentation_transform,
    fill_internal_black_gaps,
)
from hubble_workbench_app.catalogs import (
    TARGET_GALLERY,
    JWST_TARGET_GALLERY,
    TELESCOPE_CHOICES,
    SOLAR_SYSTEM_TARGETS,
    TARGET_ALIASES,
    JWST_NIRCAM_FILTERS,
    JWST_MIRI_FILTERS,
    HST_BLUE_FILTERS,
    HST_GREEN_FILTERS,
    HST_RED_FILTERS,
    RGB_FILTER_TOKENS,
    TARGET_RECIPES,
)


# ---------- Hubble Workbench Debug Logging ----------
# Set to False if you ever want to silence debug_hubble.txt without removing the code.
DEBUG_ENABLED = True



def setup_debug_logging():
    """Initialize debug_hubble.txt as early as possible for command-line and EXE runs."""
    if not DEBUG_ENABLED:
        return
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        # Avoid duplicate file handlers if this module is reloaded.
        for handler in list(root.handlers):
            if getattr(handler, "baseFilename", None) == str(DEBUG_LOG_PATH):
                root.removeHandler(handler)

        for folder in DEVELOPER_LOG_DIRS:
            folder.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            DEBUG_LOG_PATH,
            mode="a",
            maxBytes=5 * 1024 * 1024,
            backupCount=8,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(threadName)s %(funcName)s:%(lineno)d - %(message)s"
        ))
        root.addHandler(file_handler)

        logging.info("=" * 90)
        logging.info("Hubble Workbench debug logging started")
        logging.info("Debug log path: %s", DEBUG_LOG_PATH)
        logging.info("Python executable: %s", sys.executable)
        logging.info("Python version: %s", sys.version.replace("\n", " "))
        logging.info("Platform: %s", platform.platform())
        logging.info("Current working directory: %s", Path.cwd())
        logging.info("Script path: %s", Path(__file__).resolve())
        logging.info("App directory: %s", APP_DIR)
        logging.info("Command line args: %s", sys.argv)
        logging.info("Frozen executable: %s", getattr(sys, "frozen", False))
        logging.info("PyInstaller _MEIPASS: %s", getattr(sys, "_MEIPASS", None))
        logging.debug("sys.path: %s", sys.path)
    except Exception:
        # Never allow debugging itself to stop the app from opening.
        try:
            print("Failed to initialize debug logging:", traceback.format_exc())
        except Exception:
            pass


def debug_log(message, *args):
    if DEBUG_ENABLED:
        logging.debug(message, *args)


def info_log(message, *args):
    if DEBUG_ENABLED:
        logging.info(message, *args)


def warning_log(message, *args):
    if DEBUG_ENABLED:
        logging.warning(message, *args)


def log_exception(context):
    if DEBUG_ENABLED:
        logging.exception("%s", context)


def check_path(path, label="path"):
    """Log whether a required file/folder exists, then return it as a Path."""
    path = Path(path)
    try:
        if path.exists():
            debug_log("%s exists: %s", label, path)
        else:
            warning_log("%s MISSING: %s", label, path)
    except Exception:
        log_exception(f"Could not check {label}: {path}")
    return path


def safe_log_name(text, fallback="hubble"):
    text = str(text or fallback).strip() or fallback
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
    return safe[:80].strip("_") or fallback


def write_developer_json(folder, prefix, payload):
    """Save diagnostics as JSON. This must never interrupt the application."""
    try:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = folder / f"{safe_log_name(prefix)}_{stamp}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        info_log("Developer diagnostic saved: %s", path)
        return path
    except Exception:
        log_exception("Could not write developer JSON diagnostic")
        return None


def append_timing_log(label, elapsed_seconds, detail=""):
    try:
        TIMING_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = TIMING_LOG_DIR / "performance.txt"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} | {label} | {elapsed_seconds:.3f}s | {detail}\n")
    except Exception:
        log_exception("Could not append timing log")


def debug_call(func):
    """Decorator for important startup/action methods: logs entry, exit, and full crashes."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        debug_log("ENTER %s", func.__qualname__)
        started = datetime.now()
        try:
            result = func(*args, **kwargs)
            elapsed = (datetime.now() - started).total_seconds()
            debug_log("EXIT  %s after %.3fs", func.__qualname__, elapsed)
            append_timing_log(func.__qualname__, elapsed)
            return result
        except Exception:
            log_exception(f"Exception in {func.__qualname__}")
            raise
    return wrapper


def install_global_exception_logging():
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        def handle_thread_exception(args):
            logging.critical(
                "Unhandled thread exception in %s",
                getattr(args.thread, "name", "unknown-thread"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        threading.excepthook = handle_thread_exception


def log_shutdown():
    info_log("Hubble Workbench process exiting")
    logging.shutdown()


def log_environment_paths():
    info_log("Checking key project paths")
    for label, path in (
        ("Downloads folder", DOWNLOAD_DIR),
        ("Outputs folder", OUTPUT_DIR),
        ("Notes folder", NOTES_DIR),
        ("Settings file", SETTINGS_PATH),
        ("Messier list", MESSIER_LIST_PATH),
    ):
        check_path(path, label)


setup_debug_logging()
install_global_exception_logging()
atexit.register(log_shutdown)
# ---------------------------------------------------


SETTINGS = load_settings()


def optional_imports():
    debug_log("Checking optional astronomy imports")
    missing = []
    try:
        from astropy.io import fits
    except Exception:
        fits = None
        missing.append("astropy")
    try:
        from astroquery.mast import Observations
    except Exception:
        Observations = None
        missing.append("astroquery")
    if missing:
        warning_log("Missing optional dependencies: %s", missing)
    else:
        info_log("Optional astronomy dependencies loaded successfully")
    return fits, Observations, missing


FITS, OBSERVATIONS, MISSING_DEPS = optional_imports()


def first_image_hdu(path):
    if FITS is None:
        raise RuntimeError("astropy is not installed.")
    with FITS.open(path, memmap=False) as hdul:
        best_header = None
        for hdu in hdul:
            data = getattr(hdu, "data", None)
            if data is None:
                continue
            arr = np.asarray(data)
            while arr.ndim > 2:
                arr = arr[0]
            if arr.ndim == 2 and arr.size:
                best_header = hdu.header
                return arr.astype(np.float64), dict(best_header)
    raise RuntimeError(f"No 2D image data found in {path}")


def find_fits_liberator_cli():
    configured = str(SETTINGS.get("fits_liberator_cli_path", "")).strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend([
        APP_DIR / "fitscli" / "win" / "fits.exe",
        APP_DIR / "fitscli" / "fits.exe",
        APP_DIR.parent.parent / "github" / "fits-liberator-gui-master" / "fitscli" / "win" / "fits.exe",
        APP_DIR.parent.parent / "github" / "fits-liberator-cli-master" / "fitscli.exe",
        APP_DIR.parent.parent / "github" / "fits-liberator-cli-master" / "fits.exe",
    ])
    found = shutil.which("fitscli") or shutil.which("fits")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def fits_liberator_stretch_args(stretch, low, high, gamma=1.0, asinh_strength=12.0):
    stretch = (stretch or "linear").lower()
    if stretch == "sqrt":
        return "pow", "0.5", "100"
    if stretch == "pow":
        return "pow", f"{max(0.05, float(gamma)):.6g}", "100"
    if stretch == "log":
        return "log", "0.5", "100"
    if stretch == "asinh":
        return "asinh", "0.5", f"{max(0.1, float(asinh_strength)):.6g}"
    return "linear", "0.5", "100"


def read_liberated_channel(path):
    with Image.open(path) as image:
        arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    if arr.dtype == np.uint16:
        return (arr.astype(np.float32) / 65535.0).clip(0, 1)
    if arr.dtype == np.uint8:
        return (arr.astype(np.float32) / 255.0).clip(0, 1)
    arr = arr.astype(np.float32)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, dtype=np.float32)
    lo = np.nanmin(arr[finite])
    hi = np.nanmax(arr[finite])
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.float32)
    return ((arr - lo) / (hi - lo)).clip(0, 1).astype(np.float32)


def run_fits_liberator_channel(cli_path, input_path, output_path, low, high, stretch, gamma=1.0, asinh_strength=12.0):
    cli_stretch, exponent, scaled_peak = fits_liberator_stretch_args(stretch, low, high, gamma, asinh_strength)
    command = [
        str(cli_path),
        "--infile", str(input_path),
        "--outfile", str(output_path),
        "--stretch", cli_stretch,
        "--backgroundlevel", f"{float(low):.12g}",
        "--peaklevel", f"{float(high):.12g}",
        "--scaledpeaklevel", str(scaled_peak),
        "--exponent", str(exponent),
        "--depth", "16",
        "--outformat", "1",
        "--quiet", "1",
        "--undefined", "0",
        "--fastmode", "0",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=900)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"FITS Liberator failed for {Path(input_path).name}: {detail or completed.returncode}")
    if not Path(output_path).exists():
        raise RuntimeError(f"FITS Liberator did not create {Path(output_path).name}")
    return read_liberated_channel(output_path)


class HubbleWorkbench(tk.Tk):
    def __init__(self):
        info_log("Creating HubbleWorkbench Tk root")
        super().__init__()
        self.title("Space Telescope Workbench")
        self.geometry(SETTINGS.get("geometry", "1160x760"))
        self.minsize(940, 620)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.developer_mode_var = tk.BooleanVar(value=SETTINGS.get("developer_mode", True))
        self.verbose_mast_log_var = tk.BooleanVar(value=SETTINGS.get("verbose_mast_logging", True))
        self.save_search_history_var = tk.BooleanVar(value=SETTINGS.get("save_search_history", True))
        self.save_product_lists_var = tk.BooleanVar(value=SETTINGS.get("save_product_lists", True))
        self.save_download_logs_var = tk.BooleanVar(value=SETTINGS.get("save_download_logs", True))
        self.save_timing_stats_var = tk.BooleanVar(value=SETTINGS.get("save_timing_stats", True))
        self.setup_developer_menu()

        DOWNLOAD_DIR.mkdir(exist_ok=True)
        OUTPUT_DIR.mkdir(exist_ok=True)
        NOTES_DIR.mkdir(exist_ok=True)
        log_environment_paths()

        self.search_results = []
        self.product_results = []
        self.visible_product_results = []
        self.preview_photo = None
        self.rgb_photo = None
        self.browser_busy_job = None
        self.browser_timeout_job = None
        self.browser_busy_started = None
        self.browser_busy_message = ""
        self.browser_operation_id = 0
        self.browser_timeout_seconds = 180
        self.default_browser_timeout_seconds = 180
        self.last_output_path = None
        self.compose_busy_job = None
        self.view_tuned_var = tk.BooleanVar(value=True)
        self.preview_zoom_var = tk.DoubleVar(value=1.0)

        self.setup_style()
        self.build_ui()
        self.refresh_dependency_status()
        info_log("HubbleWorkbench initialization finished")

    def setup_developer_menu(self):
        """Tools menu for permanent diagnostics and developer-mode logging."""
        try:
            menu_bar = tk.Menu(self)
            tools_menu = tk.Menu(menu_bar, tearoff=0)
            tools_menu.add_checkbutton(label="Enable Developer Mode", variable=self.developer_mode_var, command=self.save_developer_settings)
            tools_menu.add_checkbutton(label="Verbose MAST Logging", variable=self.verbose_mast_log_var, command=self.save_developer_settings)
            tools_menu.add_checkbutton(label="Save Search History", variable=self.save_search_history_var, command=self.save_developer_settings)
            tools_menu.add_checkbutton(label="Save Product Lists", variable=self.save_product_lists_var, command=self.save_developer_settings)
            tools_menu.add_checkbutton(label="Save Download Logs", variable=self.save_download_logs_var, command=self.save_developer_settings)
            tools_menu.add_checkbutton(label="Timing Statistics", variable=self.save_timing_stats_var, command=self.save_developer_settings)
            tools_menu.add_separator()
            tools_menu.add_command(label="Open Logs Folder", command=lambda: self.open_folder(LOG_DIR))
            tools_menu.add_command(label="Open debug_hubble.txt", command=lambda: self.open_file(DEBUG_LOG_PATH))
            menu_bar.add_cascade(label="Tools", menu=tools_menu)
            self.config(menu=menu_bar)
            info_log("Developer Tools menu installed")
        except Exception:
            log_exception("Could not create Developer Tools menu")

    def save_developer_settings(self):
        SETTINGS["developer_mode"] = bool(self.developer_mode_var.get())
        SETTINGS["verbose_mast_logging"] = bool(self.verbose_mast_log_var.get())
        SETTINGS["save_search_history"] = bool(self.save_search_history_var.get())
        SETTINGS["save_product_lists"] = bool(self.save_product_lists_var.get())
        SETTINGS["save_download_logs"] = bool(self.save_download_logs_var.get())
        SETTINGS["save_timing_stats"] = bool(self.save_timing_stats_var.get())
        save_settings(SETTINGS)
        info_log("Developer settings saved: %s", {key: SETTINGS.get(key) for key in ("developer_mode", "verbose_mast_logging", "save_search_history", "save_product_lists", "save_download_logs", "save_timing_stats")})

    def developer_enabled(self):
        try:
            return bool(self.developer_mode_var.get())
        except Exception:
            return True

    def save_diagnostic_json(self, folder, prefix, payload):
        if not self.developer_enabled():
            return None
        return write_developer_json(folder, prefix, payload)

    def current_target_for_log(self):
        try:
            return self.target_var.get().strip() or "target"
        except Exception:
            return "target"

    def setup_style(self):
        self.configure(bg="#f3f3f3")
        self.option_add("*Font", ("Segoe UI", 10))
        self.option_add("*Listbox.Font", ("Segoe UI", 10))
        self.option_add("*Text.Font", ("Segoe UI", 10))
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            pass
        style.configure(".", font=("Segoe UI", 10), background="#f3f3f3")
        style.configure("TFrame", background="#f3f3f3")
        style.configure("TLabel", background="#f3f3f3", foreground="#1f1f1f")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1f1f1f")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#1f1f1f")
        style.configure("TNotebook", background="#f3f3f3", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 6))
        style.configure("Accent.TButton", padding=(14, 7), font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background="#f3f3f3")
        style.configure("TEntry", padding=(4, 4))
        style.configure("Horizontal.TProgressbar", thickness=8)

    def build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=12)

        self.setup_tab = ttk.Frame(self.notebook, padding=14)
        self.browser_tab = ttk.Frame(self.notebook, padding=12)
        self.observatory_tab = ttk.Frame(self.notebook, padding=12)
        self.convert_tab = ttk.Frame(self.notebook, padding=12)
        self.compose_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.setup_tab, text="Setup")
        self.notebook.add(self.browser_tab, text="MAST Browser")
        self.notebook.add(self.observatory_tab, text="Observatory Explorer")
        self.notebook.add(self.convert_tab, text="FITS Preview / Convert")
        self.notebook.add(self.compose_tab, text="Color Composer")

        self.build_setup_tab()
        self.build_browser_tab()
        self.build_observatory_tab()
        self.build_convert_tab()
        self.build_compose_tab()

    def build_setup_tab(self):
        ttk.Label(self.setup_tab, text="Space Telescope Workbench", style="Title.TLabel").pack(anchor="w")
        self.dep_text = tk.Text(
            self.setup_tab,
            height=18,
            wrap="word",
            bg="#ffffff",
            fg="#1f1f1f",
            relief="flat",
            padx=12,
            pady=12,
            insertbackground="#1f1f1f",
        )
        self.dep_text.pack(fill="both", expand=True, pady=(10, 8))
        buttons = ttk.Frame(self.setup_tab)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Refresh Status", command=self.refresh_dependency_status).pack(side="left")
        ttk.Button(buttons, text="Open Downloads Folder", command=lambda: self.open_folder(DOWNLOAD_DIR)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Open Outputs Folder", command=lambda: self.open_folder(OUTPUT_DIR)).pack(side="left", padx=(8, 0))

    def build_browser_tab(self):
        gallery = ttk.Frame(self.browser_tab)
        gallery.pack(fill="x", pady=(0, 8))
        ttk.Label(gallery, text="Telescope").pack(side="left")
        self.telescope_var = tk.StringVar(value=SETTINGS.get("telescope", "Hubble / HST"))
        telescope_combo = ttk.Combobox(
            gallery,
            textvariable=self.telescope_var,
            values=list(TELESCOPE_CHOICES.keys()),
            state="readonly",
            width=18,
        )
        telescope_combo.pack(side="left", padx=(8, 12))
        telescope_combo.bind("<<ComboboxSelected>>", self.on_telescope_changed)
        ttk.Label(gallery, text="Target Gallery").pack(side="left")
        self.target_gallery_var = tk.StringVar(value=TARGET_GALLERY[0][0])
        self.target_gallery_combo = ttk.Combobox(
            gallery,
            textvariable=self.target_gallery_var,
            values=[item[0] for item in TARGET_GALLERY],
            state="readonly",
            width=34,
        )
        self.target_gallery_combo.pack(side="left", padx=(8, 8))
        ttk.Button(gallery, text="Use Target", command=self.use_target_gallery).pack(side="left")
        ttk.Button(gallery, text="Search HLA Target", command=self.search_target_gallery_hla).pack(side="left", padx=(8, 0))

        top = ttk.Frame(self.browser_tab)
        top.pack(fill="x")
        ttk.Label(top, text="Target").pack(side="left")
        self.target_var = tk.StringVar(value=SETTINGS.get("last_target", "M51"))
        ttk.Entry(top, textvariable=self.target_var, width=28).pack(side="left", padx=(6, 8))
        ttk.Label(top, text="Radius").pack(side="left")
        self.radius_var = tk.StringVar(value=SETTINGS.get("radius", "0.05 deg"))
        ttk.Entry(top, textvariable=self.radius_var, width=10).pack(side="left", padx=(6, 8))
        self.search_button = ttk.Button(top, text="Search MAST", command=self.search_async, style="Accent.TButton")
        self.search_button.pack(side="left")
        self.easy_button = ttk.Button(top, text="Easy RGB Image", command=self.easy_rgb_async, style="Accent.TButton")
        self.easy_button.pack(side="left", padx=(8, 0))
        self.easy_hq_button = ttk.Button(top, text="Easy High Quality", command=self.easy_high_quality_async, style="Accent.TButton")
        self.easy_hq_button.pack(side="left", padx=(8, 0))
        self.hla_button = ttk.Button(top, text="Search HLA Fallback", command=self.hla_search_async)
        self.hla_button.pack(side="left", padx=(8, 0))
        self.products_button = ttk.Button(top, text="Get Products", command=self.products_async)
        self.products_button.pack(side="left", padx=(8, 0))
        self.all_products_button = ttk.Button(top, text="Get All Products", command=self.products_all_async)
        self.all_products_button.pack(side="left", padx=(8, 0))
        self.download_button = ttk.Button(top, text="Download Selected Products", command=self.download_selected_async)
        self.download_button.pack(side="left", padx=(8, 0))
        self.stop_browser_button = ttk.Button(top, text="Stop", command=self.cancel_browser_activity, state="disabled")
        self.stop_browser_button.pack(side="left", padx=(8, 0))

        source_tools = ttk.Frame(self.browser_tab)
        source_tools.pack(fill="x", pady=(6, 0))
        self.better_sources_button = ttk.Button(
            source_tools,
            text="Find Better / More Complete Image Sources",
            command=self.better_sources_async,
            style="Accent.TButton",
        )
        self.better_sources_button.pack(side="left")
        self.completeness_button = ttk.Button(
            source_tools,
            text="Completeness Check",
            command=self.completeness_check_async,
        )
        self.completeness_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            source_tools,
            text="Looks for mosaics/drizzled products, wider-radius observations, HLA products, and JWST i2d products.",
            wraplength=720,
        ).pack(side="left", padx=(12, 0))

        panes = ttk.PanedWindow(self.browser_tab, orient="horizontal")
        panes.pack(fill="both", expand=True, pady=(8, 0))

        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        ttk.Label(left, text="Observations", style="Section.TLabel").pack(anchor="w")
        self.obs_list = tk.Listbox(
            left,
            exportselection=False,
            bg="#ffffff",
            fg="#1f1f1f",
            selectbackground="#0067c0",
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        self.obs_list.pack(side="left", fill="both", expand=True)
        obs_scroll = ttk.Scrollbar(left, orient="vertical", command=self.obs_list.yview)
        obs_scroll.pack(side="right", fill="y")
        self.obs_list["yscrollcommand"] = obs_scroll.set

        product_notebook = ttk.Notebook(right)
        product_notebook.pack(fill="both", expand=True)
        product_tab = ttk.Frame(product_notebook, padding=(0, 0, 0, 0))
        rgb_tab = ttk.Frame(product_notebook, padding=(0, 0, 0, 0))
        product_notebook.add(product_tab, text="Products")
        product_notebook.add(rgb_tab, text="RGB Picker")

        ttk.Label(product_tab, text="Products", style="Section.TLabel").pack(anchor="w")
        product_filters = ttk.Frame(product_tab)
        product_filters.pack(fill="x", pady=(0, 6))
        self.direct_fits_only_var = tk.BooleanVar(value=True)
        self.hide_spectra_var = tk.BooleanVar(value=True)
        self.rgb_filters_only_var = tk.BooleanVar(value=True)
        self.rgb_sets_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            product_filters,
            text="Direct FITS only",
            variable=self.direct_fits_only_var,
            command=self.refresh_product_list,
        ).pack(side="left")
        ttk.Checkbutton(
            product_filters,
            text="Hide spectra",
            variable=self.hide_spectra_var,
            command=self.refresh_product_list,
        ).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(
            product_filters,
            text="RGB filters only",
            variable=self.rgb_filters_only_var,
            command=self.refresh_product_list,
        ).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(
            product_filters,
            text="Complete RGB sets only",
            variable=self.rgb_sets_only_var,
            command=self.refresh_product_list,
        ).pack(side="left", padx=(10, 0))
        product_box = ttk.Frame(product_tab)
        product_box.pack(fill="both", expand=True)
        self.product_list = tk.Listbox(
            product_box,
            selectmode="extended",
            exportselection=False,
            bg="#ffffff",
            fg="#1f1f1f",
            selectbackground="#0067c0",
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        self.product_list.pack(side="left", fill="both", expand=True)
        self.product_list.bind("<Control-c>", self.copy_selected_products)
        self.product_list.bind("<Control-C>", self.copy_selected_products)
        prod_scroll = ttk.Scrollbar(product_box, orient="vertical", command=self.product_list.yview)
        prod_scroll.pack(side="right", fill="y")
        self.product_list["yscrollcommand"] = prod_scroll.set
        product_actions = ttk.Frame(product_tab)
        product_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(product_actions, text="Copy Selected", command=self.copy_selected_products).pack(side="left")
        ttk.Button(product_actions, text="Copy All", command=self.copy_all_products).pack(side="left", padx=(8, 0))
        ttk.Button(product_actions, text="Select Best RGB Products", command=self.select_best_rgb_products).pack(side="left", padx=(8, 0))

        self.rgb_candidate_rows = {"blue": [], "green": [], "red": []}
        self.rgb_suggested_sets = []
        self.rgb_ready_product_ids = set()
        rgb_lists = ttk.Frame(rgb_tab)
        rgb_lists.pack(fill="both", expand=True)
        self.blue_candidate_list = self.build_rgb_candidate_column(rgb_lists, "Blue", 0)
        self.green_candidate_list = self.build_rgb_candidate_column(rgb_lists, "Green", 1)
        self.red_candidate_list = self.build_rgb_candidate_column(rgb_lists, "Red", 2)
        rgb_lists.columnconfigure(0, weight=1)
        rgb_lists.columnconfigure(1, weight=1)
        rgb_lists.columnconfigure(2, weight=1)
        ttk.Label(rgb_tab, text="Suggested RGB Sets", style="Section.TLabel").pack(anchor="w", pady=(8, 0))
        suggested_box = ttk.Frame(rgb_tab)
        suggested_box.pack(fill="x", pady=(4, 0))
        self.suggested_rgb_list = tk.Listbox(
            suggested_box,
            exportselection=False,
            height=5,
            bg="#ffffff",
            fg="#1f1f1f",
            selectbackground="#0067c0",
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        self.suggested_rgb_list.pack(side="left", fill="x", expand=True)
        suggested_scroll = ttk.Scrollbar(suggested_box, orient="vertical", command=self.suggested_rgb_list.yview)
        suggested_scroll.pack(side="right", fill="y")
        self.suggested_rgb_list["yscrollcommand"] = suggested_scroll.set
        rgb_actions = ttk.Frame(rgb_tab)
        rgb_actions.pack(fill="x", pady=(6, 0))
        ttk.Button(rgb_actions, text="Use Best Set", command=self.use_best_rgb_set, style="Accent.TButton").pack(side="left")
        ttk.Button(rgb_actions, text="Use Suggested Set", command=self.use_suggested_rgb_set).pack(side="left")
        ttk.Button(rgb_actions, text="Pick Best Available Channels", command=self.pick_best_available_rgb_channels).pack(side="left", padx=(8, 0))
        ttk.Button(rgb_actions, text="Download Selected RGB Channels", command=self.download_rgb_candidates_async).pack(side="left")
        ttk.Button(rgb_actions, text="Copy RGB Picks", command=self.copy_rgb_candidates).pack(side="left", padx=(8, 0))
        ttk.Label(
            rgb_tab,
            text="Tip: use Get All Products when blue, green, and red filters are in separate observations. Then choose one row in each RGB column and download selected RGB channels.",
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))

        self.browser_status = tk.StringVar(value="")
        self.browser_progress = ttk.Progressbar(self.browser_tab, mode="indeterminate")
        self.browser_progress.pack(fill="x", pady=(8, 0))
        self.download_progress_var = tk.DoubleVar(value=0)
        self.download_progress = ttk.Progressbar(
            self.browser_tab,
            mode="determinate",
            variable=self.download_progress_var,
            maximum=100,
        )
        self.download_progress.pack(fill="x", pady=(6, 0))
        self.download_detail = tk.StringVar(value="")
        ttk.Label(self.browser_tab, textvariable=self.download_detail).pack(anchor="w", pady=(4, 0))
        ttk.Label(self.browser_tab, textvariable=self.browser_status).pack(anchor="w", pady=(6, 0))

    def build_rgb_candidate_column(self, parent, title, column):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0))
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w")
        box = ttk.Frame(frame)
        box.pack(fill="both", expand=True, pady=(4, 0))
        candidate_list = tk.Listbox(
            box,
            exportselection=False,
            height=12,
            bg="#ffffff",
            fg="#1f1f1f",
            selectbackground="#0067c0",
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        candidate_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=candidate_list.yview)
        scroll.pack(side="right", fill="y")
        candidate_list["yscrollcommand"] = scroll.set
        return candidate_list


    def build_observatory_tab(self):
        """Version 2.0 foundation: multi-observatory overview and sky mosaic coverage."""
        ttk.Label(self.observatory_tab, text="Observatory Explorer 2.0", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.observatory_tab,
            text=(
                "Explore the target across Hubble/JWST observations, check filter coverage, "
                "and draw a first-pass sky mosaic map from MAST observation coordinates."
            ),
            wraplength=1050,
        ).pack(anchor="w", pady=(4, 10))

        controls = ttk.Frame(self.observatory_tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Analyze Current Search", command=self.observatory_analyze_current, style="Accent.TButton").pack(side="left")
        ttk.Button(controls, text="Build Sky Mosaic View", command=self.observatory_draw_current_mosaic).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Search Wider Radius", command=self.observatory_search_wider_async).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Find Better Sources", command=self.better_sources_async).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Completeness Check", command=self.completeness_check_async).pack(side="left", padx=(8, 0))

        body = ttk.PanedWindow(self.observatory_tab, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        ttk.Label(left, text="Explorer Report", style="Section.TLabel").pack(anchor="w")
        self.observatory_report_text = tk.Text(
            left,
            height=24,
            wrap="word",
            bg="#ffffff",
            fg="#1f1f1f",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.observatory_report_text.pack(fill="both", expand=True, pady=(4, 0))

        ttk.Label(right, text="Sky Mosaic / Coverage Map", style="Section.TLabel").pack(anchor="w")
        self.mosaic_canvas = tk.Canvas(right, bg="#111827", highlightthickness=0, height=520)
        self.mosaic_canvas.pack(fill="both", expand=True, pady=(4, 0))
        self.mosaic_status_var = tk.StringVar(value="Run a MAST search, then click Analyze Current Search or Build Sky Mosaic View.")
        ttk.Label(right, textvariable=self.mosaic_status_var, wraplength=720).pack(anchor="w", pady=(6, 0))
        self.mosaic_canvas.bind("<Configure>", lambda _event: self.observatory_draw_current_mosaic())

    @staticmethod
    def numeric_row_value(row, *names):
        for name in names:
            try:
                value = row.get(name, "")
            except Exception:
                value = ""
            if value in (None, ""):
                continue
            try:
                return float(value)
            except Exception:
                continue
        return None

    def observation_filter_bucket(self, row):
        text = " ".join(str(row.get(key, "")) for key in ("filters", "Spectral_Elt", "instrument_name", "obs_id"))
        upper = text.upper()
        if any(token in upper for token in HST_BLUE_FILTERS) or any(token in upper for token in ("F070W", "F090W", "F115W", "F150W")):
            return "Blue/short wavelength"
        if any(token in upper for token in HST_GREEN_FILTERS) or any(token in upper for token in ("F200W", "F277W", "F300M", "F335M")):
            return "Green/mid wavelength"
        if any(token in upper for token in HST_RED_FILTERS) or any(token in upper for token in ("F356W", "F405N", "F444W", "F560W", "F770W")):
            return "Red/IR wavelength"
        return "Unknown/other"

    def compute_observatory_summary(self, obs_rows=None, product_rows=None):
        obs_rows = list(obs_rows if obs_rows is not None else getattr(self, "search_results", []) or [])
        product_rows = list(product_rows if product_rows is not None else getattr(self, "product_results", []) or [])
        by_mission = {}
        by_instrument = {}
        by_filter = {}
        exposure_total = 0.0
        coordinate_rows = 0
        for row in obs_rows:
            mission = str(row.get("obs_collection", "Unknown") or "Unknown")
            by_mission[mission] = by_mission.get(mission, 0) + 1
            instrument = str(row.get("instrument_name", "Unknown") or "Unknown")
            by_instrument[instrument] = by_instrument.get(instrument, 0) + 1
            bucket = self.observation_filter_bucket(row)
            by_filter[bucket] = by_filter.get(bucket, 0) + 1
            try:
                exposure_total += float(row.get("t_exptime", 0) or 0)
            except Exception:
                pass
            if self.numeric_row_value(row, "s_ra", "ra", "RA") is not None and self.numeric_row_value(row, "s_dec", "dec", "DEC") is not None:
                coordinate_rows += 1

        enhanced = 0
        hla = 0
        channels = {"blue": 0, "green": 0, "red": 0}
        for row in product_rows:
            name = str(row.get("productFilename", "")).lower()
            if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
                enhanced += 1
            if row.get("_source") == "HLA":
                hla += 1
            channel = self.product_rgb_channel(row)
            if channel in channels:
                channels[channel] += 1
        rgb_sets = self.suggest_rgb_sets_for_rows(product_rows, recipe=self.target_recipe(self.target_var.get())) if product_rows else []
        return {
            "observations": len(obs_rows),
            "products": len(product_rows),
            "by_mission": by_mission,
            "by_instrument": by_instrument,
            "by_filter": by_filter,
            "exposure_total": exposure_total,
            "coordinate_rows": coordinate_rows,
            "enhanced_products": enhanced,
            "hla_products": hla,
            "channels": channels,
            "rgb_sets": len(rgb_sets),
        }

    def observatory_summary_text(self):
        target = self.target_var.get().strip() or "(no target)"
        summary = self.compute_observatory_summary()
        lines = []
        lines.append(f"Target: {target}")
        lines.append(f"Current telescope setting: {self.telescope_var.get()}")
        lines.append(f"Current radius: {self.radius_var.get()}")
        lines.append("")
        lines.append("Observations:")
        lines.append(f"- Loaded observations: {summary['observations']}")
        lines.append(f"- Observations with sky coordinates: {summary['coordinate_rows']}")
        lines.append(f"- Total exposure time listed: {summary['exposure_total']:.1f} seconds")
        lines.append("- Missions: " + (", ".join(f"{k}={v}" for k, v in sorted(summary['by_mission'].items())) or "none"))
        lines.append("- Instruments: " + (", ".join(f"{k}={v}" for k, v in sorted(summary['by_instrument'].items())[:12]) or "none"))
        lines.append("- Wavelength buckets: " + (", ".join(f"{k}={v}" for k, v in sorted(summary['by_filter'].items())) or "none"))
        lines.append("")
        lines.append("Products:")
        lines.append(f"- Loaded FITS/products: {summary['products']}")
        lines.append(f"- Mosaic/drizzled/i2d/combined candidates: {summary['enhanced_products']}")
        lines.append(f"- HLA enhanced products: {summary['hla_products']}")
        lines.append(f"- RGB channel candidates: blue={summary['channels']['blue']}, green={summary['channels']['green']}, red={summary['channels']['red']}")
        lines.append(f"- Complete RGB sets: {summary['rgb_sets']}")
        lines.append("")
        if summary["coordinate_rows"] >= 2:
            lines.append("Sky mosaic view: ready. Each plotted tile/point is an observation footprint center from MAST coordinates.")
        else:
            lines.append("Sky mosaic view: limited. Run Search Wider Radius or Find Better Sources to collect more observations with coordinates.")
        lines.append("")
        lines.append("Version 2.0 next step: this tab is the foundation for multi-telescope projects. Future upgrades can replace point footprints with true S_REGION polygons and add Chandra/GALEX/Pan-STARRS/DSS layers.")
        return "\n".join(lines)

    def observatory_analyze_current(self):
        try:
            report = self.observatory_summary_text()
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", report)
            self.observatory_draw_current_mosaic()
            self.save_diagnostic_json(SEARCH_LOG_DIR, f"{self.current_target_for_log()}_observatory_explorer", {
                "target": self.current_target_for_log(),
                "summary": self.compute_observatory_summary(),
                "report": report,
            })
        except Exception as exc:
            log_exception("Observatory Explorer analysis failed")
            messagebox.showerror("Observatory Explorer", self.format_error_message(exc))

    def observatory_draw_current_mosaic(self):
        canvas = getattr(self, "mosaic_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(400, int(canvas.winfo_width() or 700))
        height = max(300, int(canvas.winfo_height() or 500))
        rows = list(getattr(self, "search_results", []) or [])
        points = []
        for row in rows:
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            if ra is None or dec is None:
                continue
            points.append((ra, dec, row))
        canvas.create_text(width // 2, 22, text="Sky Mosaic / Coverage Map", fill="#ffffff", font=("Segoe UI", 14, "bold"))
        if not points:
            canvas.create_text(width // 2, height // 2, text="No observation coordinates loaded yet.\nRun Search MAST, Search Wider Radius, or Find Better Sources.", fill="#ffffff", font=("Segoe UI", 11), justify="center")
            self.mosaic_status_var.set("No coordinate-bearing observations available yet.")
            return
        ras = [p[0] for p in points]
        decs = [p[1] for p in points]
        ra_min, ra_max = min(ras), max(ras)
        dec_min, dec_max = min(decs), max(decs)
        if abs(ra_max - ra_min) < 1e-6:
            ra_min -= 0.001; ra_max += 0.001
        if abs(dec_max - dec_min) < 1e-6:
            dec_min -= 0.001; dec_max += 0.001
        margin = 55
        plot_w = max(1, width - margin * 2)
        plot_h = max(1, height - margin * 2)
        canvas.create_rectangle(margin, margin, width - margin, height - margin, outline="#6b7280")
        # simple grid
        for i in range(1, 5):
            x = margin + plot_w * i / 5
            y = margin + plot_h * i / 5
            canvas.create_line(x, margin, x, height - margin, fill="#1f2937")
            canvas.create_line(margin, y, width - margin, y, fill="#1f2937")
        for ra, dec, row in points[:800]:
            x = margin + (ra - ra_min) / (ra_max - ra_min) * plot_w
            y = height - margin - (dec - dec_min) / (dec_max - dec_min) * plot_h
            mission = str(row.get("obs_collection", "")).upper()
            bucket = self.observation_filter_bucket(row)
            # Use built-in Tk color names only; avoid custom style dependencies.
            fill = "cyan" if mission == "JWST" else "white"
            if "Blue" in bucket:
                fill = "skyblue"
            elif "Green" in bucket:
                fill = "lightgreen"
            elif "Red" in bucket:
                fill = "salmon"
            size = 4
            try:
                exp = float(row.get("t_exptime", 0) or 0)
                size = min(10, max(3, int(3 + math.log10(max(exp, 1)))))
            except Exception:
                pass
            canvas.create_rectangle(x - size, y - size, x + size, y + size, fill=fill, outline="#111827")
        canvas.create_text(margin, height - 28, anchor="w", text=f"RA {ra_min:.5f} to {ra_max:.5f} deg", fill="#d1d5db")
        canvas.create_text(width - margin, height - 28, anchor="e", text=f"Dec {dec_min:.5f} to {dec_max:.5f} deg", fill="#d1d5db")
        canvas.create_text(margin, 38, anchor="w", text="Color hint: blue/green/red = likely filter bucket, cyan = JWST, white = HST/other", fill="#d1d5db")
        self.mosaic_status_var.set(f"Plotted {len(points)} observation centers. This is a first-pass mosaic map; true footprint polygons are a future 2.0 upgrade.")

    def observatory_search_wider_async(self):
        if not self.require_astroquery():
            return
        target = self.target_var.get().strip()
        if not target:
            messagebox.showinfo("Observatory Explorer", "Enter a target name first.")
            return
        try:
            base = max(0.01, self.parse_degrees_radius(self.radius_var.get()))
        except Exception:
            base = 0.05
        wider = min(max(base * 3.0, 0.15), 0.75)
        telescope_code = TELESCOPE_CHOICES.get(self.telescope_var.get(), "HST")
        operation_id = self.start_browser_activity(f"Observatory Explorer: searching wider radius {wider:.2f} deg...")

        def worker():
            try:
                rows = self.mast_image_observation_rows(target, f"{wider:.6f} deg", telescope_code)
                result = (rows, wider, None)
            except Exception as exc:
                result = ([], wider, exc)
            self.after(0, lambda: self.finish_observatory_wider_search(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def finish_observatory_wider_search(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        rows, wider, error = result
        if error:
            self.stop_browser_activity(f"Observatory Explorer wider search failed: {self.format_error_message(error)}")
            return
        self.radius_var.set(f"{wider:.3f} deg")
        self.search_results = rows
        self.obs_list.delete(0, "end")
        for row in rows[:500]:
            label = (
                f"{row.get('obs_collection', '')} | {row.get('obs_id', '')} | {row.get('instrument_name', '')} | "
                f"{row.get('filters', '')} | {row.get('t_exptime', '')}s"
            )
            self.obs_list.insert("end", label)
        self.stop_browser_activity(f"Observatory Explorer found {len(rows)} observations with wider radius {wider:.3f} deg.")
        self.observatory_analyze_current()
        try:
            self.notebook.select(self.observatory_tab)
        except Exception:
            pass

    def build_convert_tab(self):
        top = ttk.Frame(self.convert_tab)
        top.pack(fill="x")
        self.convert_path_var = tk.StringVar(value="")
        ttk.Button(top, text="Choose FITS", command=self.choose_convert_file).pack(side="left")
        ttk.Entry(top, textvariable=self.convert_path_var).pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.stretch_var = tk.StringVar(value="asinh")
        ttk.Combobox(top, textvariable=self.stretch_var, values=["asinh", "pow", "sqrt", "log", "linear"], state="readonly", width=8).pack(side="left")
        ttk.Button(top, text="Preview", command=self.preview_fits_async).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Save PNG/TIFF", command=self.save_preview_outputs).pack(side="left", padx=(8, 0))

        body = ttk.PanedWindow(self.convert_tab, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(8, 0))
        image_panel = ttk.Frame(body)
        info_panel = ttk.Frame(body)
        body.add(image_panel, weight=2)
        body.add(info_panel, weight=1)

        self.preview_canvas = tk.Canvas(image_panel, bg="#111827", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.header_text = tk.Text(info_panel, wrap="word", bg="#ffffff", fg="#1f1f1f", relief="flat", padx=10, pady=10)
        self.header_text.pack(fill="both", expand=True)
        self.convert_status = tk.StringVar(value="")
        ttk.Label(self.convert_tab, textvariable=self.convert_status).pack(anchor="w", pady=(6, 0))

    def build_compose_tab(self):
        form = ttk.Frame(self.compose_tab)
        form.pack(fill="x")
        self.red_path_var = tk.StringVar()
        self.green_path_var = tk.StringVar()
        self.blue_path_var = tk.StringVar()
        for row, (label, var) in enumerate((
            ("Red channel", self.red_path_var),
            ("Green channel", self.green_path_var),
            ("Blue channel", self.blue_path_var),
        )):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=3)
            ttk.Button(form, text="Choose", command=lambda v=var: self.choose_channel(v)).grid(row=row, column=2, pady=3)
        form.columnconfigure(1, weight=1)

        controls = ttk.Frame(self.compose_tab)
        controls.pack(fill="x", pady=(6, 8))
        self.compose_stretch_var = tk.StringVar(value="asinh")
        self.high_quality_var = tk.BooleanVar(value=SETTINGS.get("high_quality_processing", True))
        self.prefer_drizzled_var = tk.BooleanVar(value=SETTINGS.get("prefer_drizzled_products", True))
        self.presentation_cleanup_var = tk.BooleanVar(value=SETTINGS.get("presentation_cleanup", True))
        self.use_fits_liberator_var = tk.BooleanVar(value=SETTINGS.get("use_fits_liberator_engine", True))
        ttk.Label(controls, text="Stretch").pack(side="left")
        ttk.Combobox(controls, textvariable=self.compose_stretch_var, values=["asinh", "pow", "sqrt", "log", "linear"], state="readonly", width=8).pack(side="left", padx=(6, 12))
        ttk.Checkbutton(controls, text="High quality 16-bit", variable=self.high_quality_var, command=self.on_quality_option_changed).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(controls, text="Prefer drizzled/mosaic", variable=self.prefer_drizzled_var, command=self.on_quality_option_changed).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(controls, text="Presentation cleanup", variable=self.presentation_cleanup_var, command=self.apply_image_tuning).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(controls, text="Use FITS Liberator if found", variable=self.use_fits_liberator_var, command=self.save_quality_settings).pack(side="left", padx=(0, 12))
        ttk.Button(controls, text="Load Latest RGB Set", command=self.load_latest_rgb_set, style="Accent.TButton").pack(side="left")
        self.auto_compose_var = tk.BooleanVar(value=SETTINGS.get("auto_compose_after_load", True))
        ttk.Checkbutton(controls, text="Auto compose", variable=self.auto_compose_var).pack(side="left", padx=(8, 10))
        ttk.Button(controls, text="Compose RGB", command=self.compose_async, style="Accent.TButton").pack(side="left")
        ttk.Button(controls, text="Save PNG/TIFF + Notes", command=self.save_composite_outputs).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Open Latest Output", command=self.open_latest_output).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Save Project", command=self.save_project_file).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Open Project", command=self.open_project_file).pack(side="left", padx=(8, 0))

        tuning = ttk.Frame(self.compose_tab)
        tuning.pack(fill="x", pady=(0, 8))
        self.black_point_var = tk.DoubleVar(value=0)
        self.brightness_var = tk.DoubleVar(value=0)
        self.contrast_var = tk.DoubleVar(value=1.0)
        self.saturation_var = tk.DoubleVar(value=1.0)
        self.red_balance_var = tk.DoubleVar(value=1.0)
        self.green_balance_var = tk.DoubleVar(value=1.0)
        self.blue_balance_var = tk.DoubleVar(value=1.0)
        self.build_tuning_slider(tuning, "Black", self.black_point_var, 0, 60, 0)
        self.build_tuning_slider(tuning, "Bright", self.brightness_var, -60, 60, 1)
        self.build_tuning_slider(tuning, "Contrast", self.contrast_var, 0.5, 2.0, 2)
        self.build_tuning_slider(tuning, "Saturation", self.saturation_var, 0, 2.5, 3)
        self.build_tuning_slider(tuning, "Red", self.red_balance_var, 0.5, 1.8, 4)
        self.build_tuning_slider(tuning, "Green", self.green_balance_var, 0.5, 1.8, 5)
        self.build_tuning_slider(tuning, "Blue", self.blue_balance_var, 0.5, 1.8, 6)

        presentation = ttk.Frame(self.compose_tab)
        presentation.pack(fill="x", pady=(0, 8))
        self.straighten_angle_var = tk.DoubleVar(value=SETTINGS.get("straighten_angle", 0.0))
        self.auto_crop_presentation_var = tk.BooleanVar(value=SETTINGS.get("auto_crop_presentation", True))
        ttk.Label(presentation, text="Straighten").pack(side="left")
        ttk.Scale(
            presentation,
            variable=self.straighten_angle_var,
            from_=-20.0,
            to=20.0,
            command=self.on_tuning_changed,
        ).pack(side="left", fill="x", expand=True, padx=(8, 6))
        self.straighten_label = ttk.Label(presentation, text=f"{self.straighten_angle_var.get():.1f} deg", width=8)
        self.straighten_label.pack(side="left")
        ttk.Button(presentation, text="Reset", command=self.reset_straighten).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            presentation,
            text="Auto crop black border",
            variable=self.auto_crop_presentation_var,
            command=self.apply_image_tuning,
        ).pack(side="left", padx=(12, 0))

        advanced = ttk.LabelFrame(self.compose_tab, text="Advanced stretch before preview")
        advanced.pack(fill="x", pady=(0, 8))
        self.channel_stretch_vars = {}
        for row, (channel, label) in enumerate((("red", "Red"), ("green", "Green"), ("blue", "Blue"))):
            ttk.Label(advanced, text=label).grid(row=row, column=0, sticky="w", padx=(8, 6), pady=3)
            low = tk.DoubleVar(value=SETTINGS.get(f"{channel}_low_percent", 0.2))
            high = tk.DoubleVar(value=SETTINGS.get(f"{channel}_high_percent", 99.8))
            gamma = tk.DoubleVar(value=SETTINGS.get(f"{channel}_gamma", 1.0))
            asinh_strength = tk.DoubleVar(value=SETTINGS.get(f"{channel}_asinh_strength", 12.0))
            self.channel_stretch_vars[channel] = {
                "low": low,
                "high": high,
                "gamma": gamma,
                "asinh": asinh_strength,
            }
            for col, (text, variable, width) in enumerate((
                ("Low %", low, 6),
                ("High %", high, 6),
                ("Gamma", gamma, 5),
                ("Asinh", asinh_strength, 5),
            ), start=1):
                ttk.Label(advanced, text=text).grid(row=row, column=col * 2 - 1, sticky="e", padx=(6, 2))
                spin = ttk.Spinbox(advanced, textvariable=variable, width=width, increment=0.1, command=self.on_stretch_setting_changed)
                spin.grid(row=row, column=col * 2, sticky="w", padx=(0, 6), pady=3)
                spin.bind("<Return>", self.on_stretch_setting_changed)
                spin.bind("<FocusOut>", self.on_stretch_setting_changed)
        ttk.Button(advanced, text="Reset Advanced Stretch", command=self.reset_advanced_stretch).grid(row=0, column=9, rowspan=3, sticky="ns", padx=(10, 8), pady=3)

        presets = ttk.Frame(self.compose_tab)
        presets.pack(fill="x", pady=(0, 8))
        ttk.Label(presets, text="Presets").pack(side="left")
        for name in ("Natural", "High Contrast", "Nebula", "Blue/Pink Nebula", "Galaxy", "Soft Stretch"):
            ttk.Button(presets, text=name, command=lambda n=name: self.apply_processing_preset(n)).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(presets, text="Show tuned image", variable=self.view_tuned_var, command=self.update_rgb_preview).pack(side="left", padx=(16, 0))
        ttk.Label(presets, text="Composite Size").pack(side="left", padx=(14, 4))
        self.composite_size_var = tk.StringVar(value=SETTINGS.get("composite_size", "Largest channel"))
        ttk.Combobox(
            presets,
            textvariable=self.composite_size_var,
            values=("Largest channel", "Smallest channel"),
            state="readonly",
            width=15,
        ).pack(side="left")
        ttk.Label(presets, text="Zoom").pack(side="left", padx=(14, 4))
        ttk.Scale(presets, variable=self.preview_zoom_var, from_=0.5, to=3.0, command=lambda _v: self.update_rgb_preview()).pack(side="left", fill="x", expand=True)

        compare = ttk.LabelFrame(self.compose_tab, text="Try Looks")
        compare.pack(fill="x", pady=(0, 8))
        self.preset_preview_canvases = {}
        for name in ("Natural", "Nebula", "Blue/Pink Nebula", "High Contrast", "Soft Stretch"):
            frame = ttk.Frame(compare)
            frame.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)
            ttk.Button(frame, text=name, command=lambda n=name: self.apply_preset_preview(n)).pack(anchor="w")
            canvas = tk.Canvas(frame, height=92, bg="#111827", highlightthickness=0)
            canvas.pack(fill="x", pady=(4, 0))
            canvas.bind("<Button-1>", lambda _event, n=name: self.apply_preset_preview(n))
            self.preset_preview_canvases[name] = canvas

        thumbs = ttk.Frame(self.compose_tab)
        thumbs.pack(fill="x", pady=(0, 8))
        self.channel_thumbnail_canvases = {}
        for label in ("Blue", "Green", "Red"):
            frame = ttk.Frame(thumbs)
            frame.pack(side="left", fill="x", expand=True, padx=(0 if label == "Blue" else 8, 0))
            ttk.Label(frame, text=f"{label} Preview", style="Section.TLabel").pack(anchor="w")
            canvas = tk.Canvas(frame, height=96, bg="#111827", highlightthickness=0)
            canvas.pack(fill="x")
            self.channel_thumbnail_canvases[label.lower()] = canvas

        self.rgb_canvas = tk.Canvas(self.compose_tab, bg="#111827", highlightthickness=0)
        self.rgb_canvas.pack(fill="both", expand=True)
        self.compose_status = tk.StringVar(value="")
        self.compose_progress = ttk.Progressbar(self.compose_tab, mode="indeterminate")
        self.compose_progress.pack(fill="x", pady=(6, 0))
        ttk.Label(self.compose_tab, textvariable=self.compose_status).pack(anchor="w", pady=(6, 0))
        self.why_var = tk.StringVar(value="")
        ttk.Label(self.compose_tab, textvariable=self.why_var, wraplength=1080).pack(anchor="w", pady=(0, 4))

    def build_tuning_slider(self, parent, label, variable, from_, to, column):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Scale(frame, variable=variable, from_=from_, to=to, command=self.on_tuning_changed).pack(fill="x")
        parent.columnconfigure(column, weight=1)

    def on_quality_option_changed(self):
        SETTINGS["high_quality_processing"] = bool(self.high_quality_var.get())
        SETTINGS["prefer_drizzled_products"] = bool(self.prefer_drizzled_var.get())
        if hasattr(self, "presentation_cleanup_var"):
            SETTINGS["presentation_cleanup"] = bool(self.presentation_cleanup_var.get())
        if hasattr(self, "straighten_angle_var"):
            SETTINGS["straighten_angle"] = float(self.straighten_angle_var.get())
        if hasattr(self, "auto_crop_presentation_var"):
            SETTINGS["auto_crop_presentation"] = bool(self.auto_crop_presentation_var.get())
        if hasattr(self, "use_fits_liberator_var"):
            SETTINGS["use_fits_liberator_engine"] = bool(self.use_fits_liberator_var.get())
        save_settings(SETTINGS)
        if hasattr(self, "product_results"):
            self.refresh_product_list()

    def on_stretch_setting_changed(self, _event=None):
        if hasattr(self, "stretch_job") and self.stretch_job:
            try:
                self.after_cancel(self.stretch_job)
            except Exception:
                pass
        self.stretch_job = self.after(120, self.recompose_if_ready)

    def recompose_if_ready(self):
        self.save_quality_settings()
        if self.auto_compose_var.get() and all(
            path.strip() for path in (self.red_path_var.get(), self.green_path_var.get(), self.blue_path_var.get())
        ):
            self.compose_async()

    def reset_advanced_stretch(self):
        for values in self.channel_stretch_vars.values():
            values["low"].set(0.2)
            values["high"].set(99.8)
            values["gamma"].set(1.0)
            values["asinh"].set(12.0)
        self.recompose_if_ready()

    def save_quality_settings(self):
        if hasattr(self, "high_quality_var"):
            SETTINGS["high_quality_processing"] = bool(self.high_quality_var.get())
        if hasattr(self, "prefer_drizzled_var"):
            SETTINGS["prefer_drizzled_products"] = bool(self.prefer_drizzled_var.get())
        if hasattr(self, "presentation_cleanup_var"):
            SETTINGS["presentation_cleanup"] = bool(self.presentation_cleanup_var.get())
        if hasattr(self, "straighten_angle_var"):
            SETTINGS["straighten_angle"] = float(self.straighten_angle_var.get())
        if hasattr(self, "auto_crop_presentation_var"):
            SETTINGS["auto_crop_presentation"] = bool(self.auto_crop_presentation_var.get())
        if hasattr(self, "use_fits_liberator_var"):
            SETTINGS["use_fits_liberator_engine"] = bool(self.use_fits_liberator_var.get())
        if hasattr(self, "channel_stretch_vars"):
            for channel, values in self.channel_stretch_vars.items():
                SETTINGS[f"{channel}_low_percent"] = float(values["low"].get())
                SETTINGS[f"{channel}_high_percent"] = float(values["high"].get())
                SETTINGS[f"{channel}_gamma"] = float(values["gamma"].get())
                SETTINGS[f"{channel}_asinh_strength"] = float(values["asinh"].get())
        save_settings(SETTINGS)

    def refresh_dependency_status(self):
        self.dep_text.delete("1.0", "end")
        if MISSING_DEPS:
            self.dep_text.insert("end", "Some astronomy dependencies are missing.\n\n")
            self.dep_text.insert("end", "Run install_dependencies.bat in this folder, then restart Space Telescope Workbench.\n\n")
            self.dep_text.insert("end", "Missing:\n")
            for item in MISSING_DEPS:
                self.dep_text.insert("end", f"- {item}\n")
            self.dep_text.insert("end", "\nAlready available:\n- numpy\n- Pillow\n")
        else:
            self.dep_text.insert("end", "All core dependencies are available.\n\n")
            self.dep_text.insert("end", "You can search MAST, download Hubble or JWST products, preview FITS files, and compose RGB images.\n")
        self.dep_text.insert("end", "\nSuggested workflow:\n")
        self.dep_text.insert("end", "1. Choose Hubble/HST or James Webb/JWST, then search a target.\n")
        self.dep_text.insert("end", "2. Select an observation and get science products.\n")
        self.dep_text.insert("end", "3. Download calibrated or drizzled FITS products.\n")
        self.dep_text.insert("end", "4. Preview individual FITS files.\n")
        self.dep_text.insert("end", "5. Assign three filters to red, green, and blue channels.\n")
        self.dep_text.insert("end", "6. Export preview PNG, high-quality TIFF, and notes.\n")

    def require_astroquery(self):
        if OBSERVATIONS is None:
            messagebox.showinfo("Dependencies", "astroquery is not installed. Run install_dependencies.bat, then restart.")
            return False
        return True

    def require_astropy(self):
        if FITS is None:
            messagebox.showinfo("Dependencies", "astropy is not installed. Run install_dependencies.bat, then restart.")
            return False
        return True

    def target_recipe(self, target):
        text = f" {target.upper()} "
        for key, recipe in TARGET_RECIPES.items():
            if f" {key} " in text or key == target.upper().strip():
                return recipe
        return None

    def apply_recipe_stretch(self, recipe):
        stretch = recipe.get("stretch", {})
        for values in self.channel_stretch_vars.values():
            values["low"].set(float(stretch.get("low", values["low"].get())))
            values["high"].set(float(stretch.get("high", values["high"].get())))
            values["gamma"].set(float(stretch.get("gamma", values["gamma"].get())))
            values["asinh"].set(float(stretch.get("asinh", values["asinh"].get())))
        preset = recipe.get("preset")
        if preset:
            self.apply_processing_preset(preset, update_status=False)

    @staticmethod
    def row_identity(row):
        return (
            str(row.get("productFilename", "")),
            str(row.get("obsID", "") or row.get("obsid", "")),
            str(row.get("dataURI", "") or row.get("dataURL", "")),
        )

    def unique_product_rows(self, rows):
        seen = set()
        unique = []
        for row in rows:
            key = self.row_identity(row)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def extra_rgb_download_rows(self, rows, rgb_set, limit=18):
        selected = {self.row_identity(rgb_set[channel]) for channel in ("blue", "green", "red")}
        candidates = []
        target_group = self.rgb_group_key(rgb_set["blue"])
        for row in rows:
            if self.row_identity(row) in selected:
                continue
            if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                continue
            if not self.product_rgb_channel(row):
                continue
            same_group = self.rgb_group_key(row) == target_group
            score = self.product_quality_score(row) + (30 if same_group else 0)
            candidates.append((-score, self.product_sort_key(row), row))
        return [row for _score, _sort, row in sorted(candidates)[:limit]]

    def quality_badges(self, row):
        name = str(row.get("productFilename", "")).lower()
        badges = []
        if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
            badges.append("Drizzled")
        try:
            size = int(float(row.get("size", 0) or 0))
        except Exception:
            size = 0
        if size >= 50_000_000:
            badges.append("Large")
        if self.product_rgb_channel(row):
            badges.append("RGB Match")
        if not self.product_is_direct_fits(row):
            badges.append("Preview Only")
        if any(token in name for token in ("raw", "uncal")):
            badges.append("Raw/Not Ideal")
        if not badges:
            badges.append("Usable")
        return badges

    def product_quality_score(self, row):
        name = str(row.get("productFilename", "")).lower()
        score = 0
        # Strongly prefer already-resampled or combined products. These are much more likely
        # to look complete than a single narrow calibrated exposure.
        for value, token in ((110, "_i2d"), (100, "_drc"), (92, "_drz"), (85, "mosaic"), (78, "combined"), (72, "coadd"), (28, "_cal"), (16, "_flc"), (12, "_flt"), (8, "rate")):
            if token in name:
                score += value
        if "raw" in name or "uncal" in name:
            score -= 70
        if self.product_rgb_channel(row):
            score += 20
        if row.get("_source") == "HLA":
            score += 35
        try:
            score += min(35, int(float(row.get("size", 0) or 0)) // 15_000_000)
        except Exception:
            pass
        return score

    def easy_choice_explanation(self, rgb_set, obs_row, recipe, high_quality, downloaded_count):
        pieces = []
        if high_quality:
            pieces.append("Easy High Quality used patient downloads, high-quality 16-bit processing, and the largest composite size.")
        if recipe:
            pieces.append(f"Target recipe: {recipe.get('name', 'known target')} with {recipe.get('preset', 'Natural')} starting look.")
        names = " ".join(str(rgb_set[channel].get("productFilename", "")).lower() for channel in ("blue", "green", "red"))
        if any(token in names for token in ("_drc", "_drz", "_i2d", "mosaic", "combined", "coadd")):
            pieces.append("Picked drizzled/mosaic-style science products because they are usually cleaner and sharper.")
        filters = []
        for channel in ("blue", "green", "red"):
            row = rgb_set[channel]
            filt = row.get("Spectral_Elt", "") or row.get("filters", "") or row.get("filter", "") or "unknown filter"
            filters.append(f"{channel} {filt}")
        pieces.append("Used " + ", ".join(filters) + ".")
        detector = obs_row.get("instrument_name", "") or rgb_set["blue"].get("Detector", "")
        if detector:
            pieces.append(f"Instrument/source: {detector}.")
        if downloaded_count > 3:
            pieces.append(f"Downloaded {downloaded_count} useful products so you can improve or reprocess this project later.")
        return "\n".join(pieces)

    def output_prefix(self):
        code = TELESCOPE_CHOICES.get(self.telescope_var.get(), "HST")
        if code == "JWST":
            return "jwst"
        if code == "BOTH":
            return "space_telescope"
        return "hubble"

    def current_gallery(self):
        return JWST_TARGET_GALLERY if TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST" else TARGET_GALLERY

    def on_telescope_changed(self, _event=None):
        SETTINGS["telescope"] = self.telescope_var.get()
        save_settings(SETTINGS)
        gallery = self.current_gallery()
        self.target_gallery_combo.configure(values=[item[0] for item in gallery])
        self.target_gallery_var.set(gallery[0][0])
        self.browser_status.set(f"Using {self.telescope_var.get()} searches.")

    def use_target_gallery(self):
        selected = self.target_gallery_var.get()
        for label, target, radius in self.current_gallery():
            if label == selected:
                self.target_var.set(target)
                self.radius_var.set(radius)
                self.browser_status.set(f"Loaded {label}.")
                return

    def search_target_gallery_hla(self):
        self.use_target_gallery()
        if TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST":
            messagebox.showinfo("HLA Fallback", "HLA fallback is Hubble-only. Use Search MAST for JWST data.")
            return
        self.hla_search_async()

    def set_browser_buttons_state(self, state):
        for button in (
            self.search_button,
            self.easy_button,
            self.easy_hq_button,
            self.hla_button,
            self.products_button,
            self.all_products_button,
            self.download_button,
        ):
            button.configure(state=state)
        for name in ("better_sources_button", "completeness_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def start_browser_activity(self, message):
        self.browser_operation_id += 1
        if self.browser_busy_job:
            try:
                self.after_cancel(self.browser_busy_job)
            except Exception:
                pass
            self.browser_busy_job = None
        self.browser_busy_message = message
        self.browser_busy_started = datetime.now()
        self.browser_progress.start(12)
        self.reset_download_progress()
        self.set_browser_buttons_state("disabled")
        self.stop_browser_button.configure(state="normal")
        if self.browser_timeout_job:
            try:
                self.after_cancel(self.browser_timeout_job)
            except Exception:
                pass
        operation_id = self.browser_operation_id
        self.browser_timeout_job = self.after(
            self.browser_timeout_seconds * 1000,
            lambda: self.browser_activity_timeout(operation_id),
        )
        self.update_browser_activity()
        return operation_id

    def extend_browser_timeout(self, operation_id):
        if operation_id != self.browser_operation_id or not self.browser_busy_started:
            return
        if self.browser_timeout_job:
            try:
                self.after_cancel(self.browser_timeout_job)
            except Exception:
                pass
        self.browser_timeout_job = self.after(
            self.browser_timeout_seconds * 1000,
            lambda: self.browser_activity_timeout(operation_id),
        )

    def update_browser_activity(self):
        if not self.browser_busy_started:
            return
        elapsed = int((datetime.now() - self.browser_busy_started).total_seconds())
        minutes, seconds = divmod(elapsed, 60)
        self.browser_status.set(
            f"{self.browser_busy_message} Active for {minutes}:{seconds:02d}. "
            "Use Stop if this is taking too long."
        )
        self.browser_busy_job = self.after(1000, self.update_browser_activity)

    def browser_activity_timeout(self, operation_id):
        if operation_id != self.browser_operation_id or not self.browser_busy_started:
            return
        minutes = max(1, self.browser_timeout_seconds // 60)
        self.cancel_browser_activity(
            f"This archive operation is taking longer than {minutes} minutes, so I stopped waiting. "
            "Try fewer products, a smaller radius, or try again in a moment."
        )

    def cancel_browser_activity(self, message=None):
        self.browser_operation_id += 1
        self.stop_browser_activity(message or "Stopped waiting for the current MAST request.")

    def reset_download_progress(self):
        if hasattr(self, "download_progress_var"):
            self.download_progress_var.set(0)
            self.download_detail.set("")

    def set_download_progress(self, operation_id, value, detail):
        if operation_id != self.browser_operation_id:
            return
        self.extend_browser_timeout(operation_id)
        self.download_progress_var.set(max(0, min(100, value)))
        self.download_detail.set(detail)

    def stop_browser_activity(self, message):
        if self.browser_busy_job:
            try:
                self.after_cancel(self.browser_busy_job)
            except Exception:
                pass
            self.browser_busy_job = None
        if self.browser_timeout_job:
            try:
                self.after_cancel(self.browser_timeout_job)
            except Exception:
                pass
            self.browser_timeout_job = None
        self.browser_busy_started = None
        self.browser_timeout_seconds = self.default_browser_timeout_seconds
        self.browser_progress.stop()
        self.set_browser_buttons_state("normal")
        self.stop_browser_button.configure(state="disabled")
        self.browser_status.set(message)

    @staticmethod
    def parse_degrees_radius(radius_text):
        text = (radius_text or "").strip().lower()
        if text.endswith("deg"):
            text = text[:-3].strip()
        elif text.endswith("d"):
            text = text[:-1].strip()
        return float(text or "0.05")

    @staticmethod
    def is_solar_system_target(target):
        return str(target or "").strip().upper() in SOLAR_SYSTEM_TARGETS

    @staticmethod
    def target_name_variants(target):
        raw = str(target or "").strip()
        variants = [raw, raw.upper(), raw.title()]
        alias = TARGET_ALIASES.get(raw.upper())
        if alias:
            variants.insert(0, alias)
            variants.extend([alias.upper(), alias.title()])
        compact = raw.replace(" ", "")
        if compact and compact != raw:
            variants.extend([compact, compact.upper()])
            compact_alias = TARGET_ALIASES.get(compact.upper())
            if compact_alias:
                variants.insert(0, compact_alias)
                variants.extend([compact_alias.upper(), compact_alias.title()])
        seen = set()
        clean = []
        for item in variants:
            key = item.strip().upper()
            if item.strip() and key not in seen:
                clean.append(item.strip())
                seen.add(key)
        return clean

    @classmethod
    def search_target_variants(cls, target):
        raw = str(target or "").strip()
        variants = cls.target_name_variants(raw)
        alias = TARGET_ALIASES.get(raw.upper())
        if alias:
            return [alias] + [item for item in variants if item.upper() != alias.upper()]
        compact = raw.replace(" ", "")
        compact_alias = TARGET_ALIASES.get(compact.upper()) if compact else None
        if compact_alias:
            return [compact_alias] + [item for item in variants if item.upper() != compact_alias.upper()]
        return variants

    def observation_row_matches_telescope(self, row, telescope_code):
        collection = str(row.get("obs_collection", "")).upper()
        if telescope_code != "BOTH" and collection != telescope_code:
            return False
        if telescope_code == "BOTH" and collection not in ("HST", "JWST"):
            return False
        return str(row.get("dataproduct_type", "")).lower() in ("image", "")

    def mast_row_dicts(self, obs_table, telescope_code):
        rows = []
        for row in obs_table:
            item = {name: self.table_value(row, name) for name in row.colnames}
            if self.observation_row_matches_telescope(item, telescope_code):
                rows.append(item)
        return rows

    def mast_target_name_rows(self, target, telescope_code):
        rows = []
        seen = set()
        collection_values = ["HST", "JWST"] if telescope_code == "BOTH" else [telescope_code]
        for name in self.target_name_variants(target):
            for collection in collection_values:
                try:
                    obs = OBSERVATIONS.query_criteria(
                        target_name=name,
                        obs_collection=collection,
                        dataproduct_type="image",
                    )
                except Exception:
                    continue
                for item in self.mast_row_dicts(obs, telescope_code):
                    key = str(item.get("obsid") or item.get("obs_id") or item)
                    if key not in seen:
                        rows.append(item)
                        seen.add(key)
        return rows

    def mast_image_observation_rows(self, target, radius, telescope_code):
        first_error = None
        rows = []
        for search_target in self.search_target_variants(target):
            try:
                obs = OBSERVATIONS.query_object(search_target, radius=radius)
                rows = self.mast_row_dicts(obs, telescope_code)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                continue
            if rows:
                return rows
        if self.is_solar_system_target(target):
            target_rows = self.mast_target_name_rows(target, telescope_code)
            if target_rows:
                return target_rows
        if first_error:
            raise first_error
        return []

    def search_async(self):
        if not self.require_astroquery():
            return
        target = self.target_var.get().strip()
        radius = self.radius_var.get().strip() or "0.05 deg"
        telescope_code = TELESCOPE_CHOICES.get(self.telescope_var.get(), "HST")
        if not target:
            messagebox.showinfo("Search MAST", "Enter a target name.")
            return
        SETTINGS["last_target"] = target
        SETTINGS["radius"] = radius
        SETTINGS["telescope"] = self.telescope_var.get()
        save_settings(SETTINGS)
        telescope_label = self.telescope_var.get()
        operation_id = self.start_browser_activity(f"Searching MAST for {telescope_label} observations...")
        self.obs_list.delete(0, "end")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                rows = self.mast_image_observation_rows(target, radius, telescope_code)
                result = (rows, None)
            except Exception as exc:
                result = ([], exc)
            self.after(0, lambda: self.finish_search(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def easy_high_quality_async(self):
        self.easy_rgb_async(high_quality=True)

    def easy_rgb_async(self, high_quality=False):
        if not self.require_astroquery() or not self.require_astropy():
            return
        target = self.target_var.get().strip()
        radius = self.radius_var.get().strip() or "0.05 deg"
        telescope_code = TELESCOPE_CHOICES.get(self.telescope_var.get(), "HST")
        if not target:
            messagebox.showinfo("Easy RGB Image", "Choose a target first.")
            return
        SETTINGS["last_target"] = target
        SETTINGS["radius"] = radius
        SETTINGS["telescope"] = self.telescope_var.get()
        save_settings(SETTINGS)
        recipe = self.target_recipe(target)
        if high_quality:
            self.high_quality_var.set(True)
            self.prefer_drizzled_var.set(True)
            self.composite_size_var.set("Largest channel")
            if recipe:
                self.apply_recipe_stretch(recipe)
        self.browser_timeout_seconds = 1800 if high_quality else 600
        label = "Easy High Quality" if high_quality else "Easy RGB"
        operation_id = self.start_browser_activity(f"{label}: searching {target}...")
        self.obs_list.delete(0, "end")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                obs_rows = self.mast_image_observation_rows(target, radius, telescope_code)
                if not obs_rows:
                    raise RuntimeError("No image observations found for this target.")

                best = None
                checked = 0
                for obs_row in obs_rows[:25]:
                    checked += 1
                    self.after(0, lambda c=checked, total=min(25, len(obs_rows)): self.set_download_progress(operation_id, min(40, c / total * 40), f"Checking observation {c} of {total} for RGB products..."))
                    obsid = obs_row.get("obsid")
                    products = OBSERVATIONS.get_product_list(obsid)
                    rows = [self.normalize_product_row({name: self.table_value(row, name) for name in row.colnames}, obs_row) for row in products]
                    rows = [
                        item for item in rows
                        if str(item.get("productFilename", "")).lower().endswith((".fits", ".fits.gz"))
                    ]
                    rows.sort(key=self.product_sort_key)
                    rgb_sets = self.suggest_rgb_sets_for_rows(rows, recipe=recipe)
                    if rgb_sets:
                        candidate = rgb_sets[0]
                        score = self.rgb_set_score(candidate, recipe=recipe)
                        if best is None or score > best[0]:
                            best = (score, obs_row, rows, candidate)
                            if score >= (140 if high_quality else 100):
                                break
                if best is None:
                    if telescope_code in ("HST", "BOTH"):
                        self.after(0, lambda: self.set_download_progress(operation_id, 42, "Trying Hubble Legacy Archive fallback for RGB products..."))
                        hla_rows = self.fetch_hla_product_rows(target, radius)
                        rgb_sets = self.suggest_rgb_sets_for_rows(hla_rows, recipe=recipe)
                        if rgb_sets:
                            best = (self.rgb_set_score(rgb_sets[0], recipe=recipe), {"obs_id": "HLA fallback", "obs_collection": "HST"}, hla_rows, rgb_sets[0])
                    if best is None:
                        raise RuntimeError("No complete RGB-ready product set was found. Try a different target or larger radius.")

                _score, obs_row, rows, rgb_set = best
                target_folder = target.replace(" ", "_") or "target"
                download_path = DOWNLOAD_DIR / f"{target_folder}_Easy_RGB" / datetime.now().strftime("%Y%m%d_%H%M%S")
                download_path.mkdir(parents=True, exist_ok=True)
                selected_rows = [rgb_set[channel] for channel in ("blue", "green", "red")]
                extra_rows = self.extra_rgb_download_rows(rows, rgb_set, limit=18) if high_quality else []
                download_rows = self.unique_product_rows(selected_rows + extra_rows)
                detail = "Downloading best RGB set plus extra matching products..." if high_quality and extra_rows else "Downloading best RGB set..."
                self.after(0, lambda d=detail: self.set_download_progress(operation_id, 45, d))
                if selected_rows and selected_rows[0].get("_source") == "HLA":
                    manifest = self.download_hla_products(download_rows, download_path, operation_id)
                else:
                    manifest = OBSERVATIONS.download_products(download_rows, download_dir=str(download_path), cache=True)
                downloaded = self.extract_downloaded_paths(manifest, download_path)
                channel_paths = self.match_downloaded_rgb_paths(downloaded, rgb_set)
                if any(channel not in channel_paths for channel in ("blue", "green", "red")):
                    raise RuntimeError("Downloaded RGB files, but could not match all channels on disk.")

                self.after(0, lambda: self.set_download_progress(operation_id, 80, "Composing RGB image..."))
                image, headers, source_shapes, resize_mode, rgb_float, _engine_note = self.compose_rgb_from_paths([
                    channel_paths["red"],
                    channel_paths["green"],
                    channel_paths["blue"],
                ])
                base_image, base_float = self.prepare_compose_working_copy(image, rgb_float)
                result = {
                    "obs_rows": obs_rows,
                    "obs": obs_row,
                    "products": rows,
                    "rgb_set": rgb_set,
                    "channel_paths": channel_paths,
                    "image": image,
                    "rgb_float": rgb_float,
                    "base_image": base_image,
                    "base_float": base_float,
                    "headers": headers,
                    "source_shapes": source_shapes,
                    "resize_mode": resize_mode,
                    "download_path": download_path,
                    "why": self.easy_choice_explanation(rgb_set, obs_row, recipe, high_quality, len(download_rows)),
                    "high_quality_easy": high_quality,
                }
                self.after(0, lambda: self.finish_easy_rgb(operation_id, result, None))
            except Exception as exc:
                error_detail = traceback.format_exc()
                self.after(0, lambda exc=exc, error_detail=error_detail: self.finish_easy_rgb(operation_id, None, exc, error_detail))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def table_value(row, name):
        value = row[name]
        try:
            mask = getattr(value, "mask", False)
            if np.all(mask):
                return ""
        except Exception:
            pass
        try:
            if hasattr(value, "filled"):
                value = value.filled("")
        except Exception:
            pass
        try:
            arr = np.asarray(value)
            if arr.shape == ():
                value = arr.item()
            elif arr.size == 1:
                value = arr.reshape(-1)[0].item()
            else:
                return ",".join(str(item) for item in arr.reshape(-1).tolist())
        except Exception:
            try:
                if hasattr(value, "item"):
                    value = value.item()
            except Exception:
                pass
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return value

    def finish_search(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        rows, error = result
        if error:
            if TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST":
                self.stop_browser_activity(f"MAST search failed: {error}")
            else:
                self.hla_search_async(fallback_message=f"MAST search failed: {error}. Trying HLA fallback...")
            return
        self.search_results = rows
        for row in rows[:500]:
            label = (
                f"{row.get('obs_collection', '')} | {row.get('obs_id', '')} | {row.get('instrument_name', '')} | "
                f"{row.get('filters', '')} | {row.get('t_exptime', '')}s"
            )
            self.obs_list.insert("end", label)
        if self.save_search_history_var.get():
            self.save_diagnostic_json(SEARCH_LOG_DIR, f"{self.current_target_for_log()}_observations", {
                "target": self.current_target_for_log(),
                "radius": self.radius_var.get(),
                "telescope": self.telescope_var.get(),
                "count": len(rows),
                "observations": rows[:1000],
            })
        self.stop_browser_activity(f"Found {len(rows)} image observations. Select one, then choose Get Products.")

    def hla_search_async(self, fallback_message=None):
        if not self.require_astropy():
            return
        if not fallback_message and TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST":
            messagebox.showinfo("HLA Fallback", "The Hubble Legacy Archive fallback is Hubble-only. Use Search MAST for JWST data.")
            return
        target = self.target_var.get().strip()
        radius = self.radius_var.get().strip() or "0.05 deg"
        if not target:
            messagebox.showinfo("Search HLA", "Enter a target name.")
            return
        SETTINGS["last_target"] = target
        SETTINGS["radius"] = radius
        save_settings(SETTINGS)
        operation_id = self.start_browser_activity(fallback_message or "Searching Hubble Legacy Archive products...")
        self.obs_list.delete(0, "end")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                rows = self.fetch_hla_product_rows(target, radius)
                result = (rows, None)
            except Exception as exc:
                result = ([], exc)
            self.after(0, lambda: self.finish_hla_search(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def fetch_hla_product_rows(self, target, radius):
        from astropy.coordinates import SkyCoord
        from astropy.io.votable import parse_single_table

        last_error = None
        coord = None
        for search_target in self.search_target_variants(target):
            try:
                coord = SkyCoord.from_name(search_target)
                break
            except Exception as exc:
                last_error = exc
        if coord is None:
            raise last_error or RuntimeError(f"Could not resolve target: {target}")
        size = self.parse_degrees_radius(radius)
        query = urllib.parse.urlencode({
            "POS": f"{coord.ra.deg},{coord.dec.deg}",
            "SIZE": str(size),
            "FORMAT": "ALL",
        })
        url = f"https://hla.stsci.edu/cgi-bin/hlaSIAP.cgi?{query}"
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        table = parse_single_table(io.BytesIO(payload)).to_table()
        rows = []
        for row in table:
            item = {name: self.table_value(row, name) for name in table.colnames}
            product_url = html.unescape(str(item.get("URL", "")))
            dataset = str(item.get("Dataset", "")).strip()
            if not product_url or not dataset:
                continue
            item["_source"] = "HLA"
            item["URL"] = product_url
            item["productFilename"] = self.hla_filename(item)
            item["productSubGroupDescription"] = (
                f"HLA {item.get('Detector', '')} {item.get('Spectral_Elt', '')}".strip()
            )
            rows.append(item)
        rows.sort(key=self.hla_sort_key)
        return rows

    @staticmethod
    def hla_filename(item):
        dataset = str(item.get("Dataset", "hla_product")).strip() or "hla_product"
        fmt = str(item.get("Format", "")).lower()
        if "jpeg" in fmt or "jpg" in fmt:
            suffix = ".jpg"
        elif "png" in fmt:
            suffix = ".png"
        elif "tar" in fmt:
            suffix = ".tar"
        elif dataset.lower().endswith((".fits", ".fit", ".fits.gz", ".jpg", ".jpeg", ".png", ".tar")):
            suffix = ""
        else:
            suffix = ".fits"
        return f"{dataset}{suffix}"

    @staticmethod
    def hla_sort_key(item):
        level = str(item.get("Level", "9"))
        name = str(item.get("productFilename", "")).lower()
        fmt = str(item.get("Format", "")).lower()
        fits_priority = 0 if "fits" in fmt or name.endswith((".fits", ".fits.gz")) else 1
        return fits_priority, level, name

    def product_label(self, row):
        badges = " ".join(f"[{badge}]" for badge in self.quality_badges(row))
        if row.get("_source") == "HLA":
            return (
                f"{badges} "
                f"{row.get('productFilename', '')} | {row.get('Target', '')} | "
                f"{row.get('Detector', '')} | {row.get('Spectral_Elt', '')} | {row.get('Format', '')}"
            )
        return (
            f"{badges} "
            f"{row.get('obs_collection', '') or row.get('mission', '')} | {row.get('productFilename', '')} | "
            f"{row.get('productSubGroupDescription', '')} | {row.get('filters', '') or row.get('filter', '')} | {row.get('size', '')}"
        )

    @staticmethod
    def product_filter_text(row):
        return " ".join(str(row.get(key, "")) for key in (
            "productFilename",
            "productSubGroupDescription",
            "productType",
            "Spectral_Elt",
            "filters",
            "filter",
            "Format",
            "Detector",
            "instrument_name",
        )).upper()

    @staticmethod
    def product_filter_name(row):
        return str(row.get("Spectral_Elt", "") or row.get("filters", "") or row.get("filter", "")).upper()

    def jwst_filter_wavelengths(self, row):
        text = self.product_filter_text(row)
        wavelengths = []
        for token, wavelength in {**JWST_NIRCAM_FILTERS, **JWST_MIRI_FILTERS}.items():
            if token in text:
                wavelengths.append((token, wavelength))
        return wavelengths

    def product_rgb_channel(self, row):
        text = self.product_filter_text(row)
        jwst_filters = self.jwst_filter_wavelengths(row)
        if jwst_filters:
            detector_text = str(row.get("Detector", "") or row.get("instrument_name", "")).upper()
            wavelength = min(value for _token, value in jwst_filters)
            if "MIRI" in detector_text or any(token in JWST_MIRI_FILTERS for token, _value in jwst_filters):
                if wavelength <= 8.0:
                    return "blue"
                if wavelength <= 15.0:
                    return "green"
                return "red"
            if wavelength < 1.8:
                return "blue"
            if wavelength < 3.2:
                return "green"
            return "red"
        if any(token in text for token in HST_BLUE_FILTERS):
            return "blue"
        if any(token in text for token in HST_GREEN_FILTERS):
            return "green"
        if any(token in text for token in HST_RED_FILTERS):
            return "red"
        return None

    def product_is_direct_fits(self, row):
        fmt = str(row.get("Format", "")).lower()
        name = str(row.get("productFilename", "")).lower()
        if "text/html" in fmt:
            return False
        return "image/fits" in fmt or name.endswith((".fits", ".fits.gz"))

    def product_is_spectrum(self, row):
        text = self.product_filter_text(row)
        return any(token in text for token in ("G102", "G141", "G230", "G430", "G750", "GRISM", "PRISM", "SPECTR", "NRS", "MRS", "IFU"))

    def rgb_candidate_label(self, row):
        return (
            f"{row.get('Spectral_Elt', '') or row.get('filters', '')} | "
            f"{row.get('Target', '') or row.get('target_name', '') or row.get('obs_id', '')} | "
            f"{row.get('Detector', '') or row.get('instrument_name', '')} | "
            f"{row.get('productFilename', '')}"
        )

    @staticmethod
    def rgb_group_key(row):
        target = str(row.get("Target", "") or row.get("target_name", "") or row.get("obs_id", "")).strip()
        detector = str(row.get("Detector", "") or row.get("instrument_name", "")).strip()
        name = str(row.get("productFilename", "") or row.get("obs_id", "")).strip()
        parts = name.split("_")
        prefix = "_".join(parts[:3]) if len(parts) >= 3 else name[:12]
        return target, detector, prefix

    @staticmethod
    def suggested_rgb_label(rgb_set):
        blue = rgb_set["blue"]
        green = rgb_set["green"]
        red = rgb_set["red"]
        target = blue.get("Target", "") or blue.get("obs_id", "")
        detector = blue.get("Detector", "") or blue.get("instrument_name", "")
        return (
            f"{target} | {detector} | "
            f"B {blue.get('Spectral_Elt', '')}  G {green.get('Spectral_Elt', '')}  R {red.get('Spectral_Elt', '')}"
        )

    def rgb_set_score(self, rgb_set, recipe=None):
        score = 0
        detector_text = " ".join(str(rgb_set[channel].get("Detector", "") or rgb_set[channel].get("instrument_name", "")) for channel in ("blue", "green", "red")).upper()
        filter_text = " ".join(str(rgb_set[channel].get("Spectral_Elt", "") or rgb_set[channel].get("filters", "")) for channel in ("blue", "green", "red")).upper()
        target_text = " ".join(str(rgb_set[channel].get("Target", "") or rgb_set[channel].get("obs_id", "")) for channel in ("blue", "green", "red")).upper()
        filename_text = " ".join(str(rgb_set[channel].get("productFilename", "")) for channel in ("blue", "green", "red")).lower()
        if "ACS/WFC" in detector_text:
            score += 40
        if "WFC3/UVIS" in detector_text:
            score += 35
        if "WFPC2" in detector_text:
            score += 20
        if "NIRCAM" in detector_text:
            score += 45
        if "MIRI" in detector_text:
            score += 38
        jwst_wavelengths = []
        for channel in ("blue", "green", "red"):
            values = self.jwst_filter_wavelengths(rgb_set[channel])
            if values:
                jwst_wavelengths.append(min(value for _token, value in values))
        if len(jwst_wavelengths) == 3:
            spread = max(jwst_wavelengths) - min(jwst_wavelengths)
            score += min(35, int(spread * 8))
            if max(jwst_wavelengths) <= 5.0:
                score += 18
            elif min(jwst_wavelengths) >= 5.0:
                score += 15
            else:
                score += 10
            if jwst_wavelengths == sorted(jwst_wavelengths):
                score += 12
        if "_drc" in filename_text:
            score += 45
        if "_drz" in filename_text:
            score += 40
        if "_i2d" in filename_text:
            score += 35
        if "_cal" in filename_text:
            score += 20
        if any(token in filename_text for token in ("mosaic", "combined", "coadd")):
            score += 30
        for token in ("DARK", "CALIB", "ANY"):
            if token in target_text:
                score -= 40
        for token in ("F435W", "F438W", "F439W", "F475W", "F090W", "F115W", "F150W"):
            if token in filter_text:
                score += 12
        for token in ("F555W", "F606W", "F200W", "F277W", "F335M", "F1000W", "F1130W", "F1280W"):
            if token in filter_text:
                score += 12
        for token in ("F814W", "F850LP", "F356W", "F444W", "F1500W", "F1800W", "F2100W"):
            if token in filter_text:
                score += 12
        if all(self.product_is_direct_fits(rgb_set[channel]) for channel in ("blue", "green", "red")):
            score += 25
        if recipe:
            filters = recipe.get("filters", {})
            for channel in ("blue", "green", "red"):
                wanted = filters.get(channel, ())
                text = self.product_filter_text(rgb_set[channel])
                if any(token in text for token in wanted):
                    score += 22
        return score

    def product_matches_filters(self, row):
        text = self.product_filter_text(row)
        if self.direct_fits_only_var.get():
            if not self.product_is_direct_fits(row):
                return False
        if self.hide_spectra_var.get():
            if self.product_is_spectrum(row):
                return False
        if self.rgb_filters_only_var.get():
            if not any(token in text for token in RGB_FILTER_TOKENS):
                return False
        if self.rgb_sets_only_var.get():
            if id(row) not in self.rgb_ready_product_ids:
                return False
        return True

    def refresh_product_list(self):
        if not hasattr(self, "product_list"):
            return
        self.update_rgb_ready_product_ids()
        self.product_list.delete(0, "end")
        self.visible_product_results = [
            row for row in self.product_results
            if self.product_matches_filters(row)
        ]
        for row in self.visible_product_results[:1000]:
            self.product_list.insert("end", self.product_label(row))
        self.refresh_rgb_candidates()
        total = len(self.product_results)
        visible = len(self.visible_product_results)
        if total:
            self.browser_status.set(f"Showing {visible} of {total} products with the current filters.")

    def update_rgb_ready_product_ids(self):
        self.rgb_ready_product_ids = set()
        groups = {}
        for row in self.product_results:
            if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                continue
            channel = self.product_rgb_channel(row)
            if not channel:
                continue
            group = groups.setdefault(self.rgb_group_key(row), {"blue": [], "green": [], "red": []})
            group[channel].append(row)
        for group in groups.values():
            if group["blue"] and group["green"] and group["red"]:
                for channel in ("blue", "green", "red"):
                    for row in group[channel]:
                        self.rgb_ready_product_ids.add(id(row))

    def refresh_rgb_candidates(self):
        if not hasattr(self, "blue_candidate_list"):
            return
        self.rgb_candidate_rows = {"blue": [], "green": [], "red": []}
        self.rgb_suggested_sets = []
        for widget in (self.blue_candidate_list, self.green_candidate_list, self.red_candidate_list):
            widget.delete(0, "end")
        self.suggested_rgb_list.delete(0, "end")
        for row in self.product_results:
            if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                continue
            channel = self.product_rgb_channel(row)
            if channel:
                self.rgb_candidate_rows[channel].append(row)
        for channel, widget in (
            ("blue", self.blue_candidate_list),
            ("green", self.green_candidate_list),
            ("red", self.red_candidate_list),
        ):
            for row in self.rgb_candidate_rows[channel][:300]:
                widget.insert("end", self.rgb_candidate_label(row))
            if widget.size():
                widget.selection_set(0)
        groups = {}
        for channel, rows in self.rgb_candidate_rows.items():
            for row in rows:
                group = groups.setdefault(self.rgb_group_key(row), {"blue": [], "green": [], "red": []})
                group[channel].append(row)
        for group in groups.values():
            if group["blue"] and group["green"] and group["red"]:
                self.rgb_suggested_sets.append({
                    "blue": group["blue"][0],
                    "green": group["green"][0],
                    "red": group["red"][0],
                })
        if not self.rgb_suggested_sets and all(self.rgb_candidate_rows[channel] for channel in ("blue", "green", "red")):
            self.rgb_suggested_sets.append({
                "blue": self.best_rgb_candidate("blue"),
                "green": self.best_rgb_candidate("green"),
                "red": self.best_rgb_candidate("red"),
            })
        self.rgb_suggested_sets.sort(key=lambda rgb_set: self.rgb_set_score(rgb_set, self.target_recipe(self.target_var.get())), reverse=True)
        for rgb_set in self.rgb_suggested_sets[:100]:
            self.suggested_rgb_list.insert("end", self.suggested_rgb_label(rgb_set))
        if self.suggested_rgb_list.size():
            self.suggested_rgb_list.selection_set(0)

    def best_rgb_candidate(self, channel):
        rows = self.rgb_candidate_rows.get(channel, [])
        if not rows:
            return None
        return sorted(rows, key=lambda row: (-self.product_quality_score(row), self.product_sort_key(row)))[0]

    def suggest_rgb_sets_for_rows(self, rows, recipe=None):
        candidate_rows = {"blue": [], "green": [], "red": []}
        for row in rows:
            if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                continue
            channel = self.product_rgb_channel(row)
            if channel:
                candidate_rows[channel].append(row)
        groups = {}
        for channel, channel_rows in candidate_rows.items():
            for row in channel_rows:
                group = groups.setdefault(self.rgb_group_key(row), {"blue": [], "green": [], "red": []})
                group[channel].append(row)
        rgb_sets = []
        for group in groups.values():
            if group["blue"] and group["green"] and group["red"]:
                rgb_sets.append({
                    "blue": group["blue"][0],
                    "green": group["green"][0],
                    "red": group["red"][0],
                })
        if not rgb_sets and all(candidate_rows[channel] for channel in ("blue", "green", "red")):
            rgb_sets.append({
                "blue": candidate_rows["blue"][0],
                "green": candidate_rows["green"][0],
                "red": candidate_rows["red"][0],
            })
        rgb_sets.sort(key=lambda rgb_set: self.rgb_set_score(rgb_set, recipe), reverse=True)
        return rgb_sets

    def select_rgb_candidate_row(self, channel, row):
        widget = {
            "blue": self.blue_candidate_list,
            "green": self.green_candidate_list,
            "red": self.red_candidate_list,
        }[channel]
        rows = self.rgb_candidate_rows.get(channel, [])
        for index, candidate in enumerate(rows[:300]):
            if candidate is row:
                widget.selection_clear(0, "end")
                widget.selection_set(index)
                widget.see(index)
                return

    def use_suggested_rgb_set(self):
        selection = self.suggested_rgb_list.curselection()
        if not selection:
            self.browser_status.set("No suggested RGB set is selected.")
            return
        rgb_set = self.rgb_suggested_sets[selection[0]]
        for channel in ("blue", "green", "red"):
            self.select_rgb_candidate_row(channel, rgb_set[channel])
        self.browser_status.set("Selected the suggested RGB set.")

    def use_best_rgb_set(self):
        if not self.rgb_suggested_sets:
            self.browser_status.set("No complete RGB set was found yet.")
            return
        self.suggested_rgb_list.selection_clear(0, "end")
        self.suggested_rgb_list.selection_set(0)
        self.suggested_rgb_list.see(0)
        self.use_suggested_rgb_set()

    def pick_best_available_rgb_channels(self):
        missing = [channel for channel in ("blue", "green", "red") if not self.rgb_candidate_rows.get(channel)]
        if missing:
            self.browser_status.set(f"Missing {', '.join(missing)} candidates. Try Get All Products or uncheck strict filters.")
            return
        for channel in ("blue", "green", "red"):
            self.select_rgb_candidate_row(channel, self.best_rgb_candidate(channel))
        self.browser_status.set("Picked the best available blue, green, and red channels. Choose Download Selected RGB Channels.")

    def select_best_rgb_products(self):
        if not self.rgb_suggested_sets:
            self.pick_best_available_rgb_channels()
            return
        rgb_set = self.rgb_suggested_sets[0]
        wanted = {id(rgb_set[channel]) for channel in ("blue", "green", "red")}
        grouped_set = all(row_id in self.rgb_ready_product_ids for row_id in wanted)
        if grouped_set and not self.rgb_sets_only_var.get():
            self.rgb_sets_only_var.set(True)
            self.refresh_product_list()
        elif not grouped_set and self.rgb_sets_only_var.get():
            self.rgb_sets_only_var.set(False)
            self.refresh_product_list()
        self.product_list.selection_clear(0, "end")
        selected_count = 0
        for index, row in enumerate(self.visible_product_results):
            if id(row) in wanted:
                self.product_list.selection_set(index)
                self.product_list.see(index)
                selected_count += 1
        self.use_best_rgb_set()
        self.browser_status.set(f"Selected {selected_count} best RGB products. Choose Download Selected Products or Download RGB Set.")

    def finish_hla_search(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        rows, error = result
        if error:
            self.stop_browser_activity(f"HLA search failed: {error}")
            return
        self.search_results = []
        self.product_results = rows
        self.obs_list.insert("end", "HLA search returned direct downloadable products.")
        self.obs_list.insert("end", "Select one or more products on the right, then choose Download Selected Products.")
        self.refresh_product_list()
        self.stop_browser_activity(
            f"Found {len(rows)} HLA products. Showing {len(self.visible_product_results)} with the current filters."
        )

    def copy_selected_products(self, event=None):
        selections = self.product_list.curselection()
        if not selections:
            self.browser_status.set("Select one or more products first, then copy.")
            return "break"
        self.copy_product_indexes(selections, "selected")
        return "break"

    def copy_all_products(self):
        count = self.product_list.size()
        if not count:
            self.browser_status.set("There are no products to copy yet.")
            return
        self.copy_product_indexes(range(count), "all")

    def copy_product_indexes(self, indexes, label):
        lines = []
        for index in indexes:
            visible = self.product_list.get(index)
            lines.append(visible)
            if index < len(self.visible_product_results):
                details = self.product_copy_details(self.visible_product_results[index])
                if details:
                    lines.extend(f"  {line}" for line in details)
            lines.append("")
        text = "\n".join(lines).strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.browser_status.set(f"Copied {label} product information to the clipboard.")

    def selected_rgb_rows(self):
        picks = []
        for channel, widget in (
            ("blue", self.blue_candidate_list),
            ("green", self.green_candidate_list),
            ("red", self.red_candidate_list),
        ):
            selection = widget.curselection()
            if not selection:
                messagebox.showinfo("RGB Picker", f"Select one {channel} product first.")
                return None
            rows = self.rgb_candidate_rows.get(channel, [])
            index = selection[0]
            if index >= len(rows):
                messagebox.showinfo("RGB Picker", f"The selected {channel} product is no longer available.")
                return None
            picks.append((channel, rows[index]))
        return picks

    def copy_rgb_candidates(self):
        picks = self.selected_rgb_rows()
        if not picks:
            return
        lines = []
        for channel, row in picks:
            lines.append(f"{channel.title()}: {self.rgb_candidate_label(row)}")
            lines.extend(f"  {line}" for line in self.product_copy_details(row))
            lines.append("")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines).strip())
        self.update()
        self.browser_status.set("Copied the selected RGB picks to the clipboard.")

    def download_rgb_candidates_async(self):
        picks = self.selected_rgb_rows()
        if not picks:
            return
        rgb_set = {channel: row for channel, row in picks}
        rows = [rgb_set[channel] for channel in ("blue", "green", "red")]
        self.download_product_rows_async(rows, "RGB_set", rgb_set=rgb_set)

    @staticmethod
    def product_copy_details(row):
        details = []
        for key in (
            "Dataset",
            "Target",
            "Detector",
            "Spectral_Elt",
            "Format",
            "Level",
            "ExpTime",
            "StartTime",
            "productFilename",
            "productSubGroupDescription",
            "size",
            "URL",
        ):
            value = row.get(key, "")
            if value not in ("", None):
                details.append(f"{key}: {value}")
        return details


    def better_sources_async(self):
        if not self.require_astroquery() or not self.require_astropy():
            return
        target = self.target_var.get().strip()
        if not target:
            messagebox.showinfo("Find Better Sources", "Enter a target name first.")
            return
        base_radius = self.radius_var.get().strip() or "0.05 deg"
        telescope_code = TELESCOPE_CHOICES.get(self.telescope_var.get(), "HST")
        try:
            base_degrees = max(0.01, self.parse_degrees_radius(base_radius))
        except Exception:
            base_degrees = 0.05
        radii = []
        for value in (base_degrees, base_degrees * 2.0, base_degrees * 4.0):
            value = min(0.35, max(0.01, value))
            if value not in radii:
                radii.append(value)
        SETTINGS["last_target"] = target
        SETTINGS["radius"] = base_radius
        SETTINGS["telescope"] = self.telescope_var.get()
        save_settings(SETTINGS)
        self.browser_timeout_seconds = 2400
        operation_id = self.start_browser_activity("Searching wider sky area for better combined products...")
        self.obs_list.delete(0, "end")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                report = []
                obs_rows = []
                seen_obs = set()
                for radius in radii:
                    self.after(0, lambda r=radius: self.set_download_progress(operation_id, 5, f"Searching MAST within {r:.3f} deg..."))
                    try:
                        rows = self.mast_image_observation_rows(target, f"{radius:.6f} deg", telescope_code)
                    except Exception as exc:
                        report.append(f"MAST radius {radius:.3f} deg failed: {exc}")
                        continue
                    for row in rows:
                        key = str(row.get("obsid") or row.get("obs_id") or row)
                        if key not in seen_obs:
                            seen_obs.add(key)
                            obs_rows.append(row)
                    report.append(f"MAST radius {radius:.3f} deg: {len(rows)} image observations")

                product_rows = []
                seen_products = set()
                scan_rows = obs_rows[:80]
                total = max(1, len(scan_rows))
                for index, obs in enumerate(scan_rows, start=1):
                    obsid = obs.get("obsid")
                    obs_label = obs.get("obs_id") or obsid or f"observation {index}"
                    self.after(0, lambda i=index, t=total, label=obs_label: self.set_download_progress(
                        operation_id,
                        10 + min(70, i / t * 70),
                        f"Checking products {i} of {t}: {label}",
                    ))
                    if not obsid:
                        continue
                    try:
                        products = OBSERVATIONS.get_product_list(obsid)
                    except Exception:
                        continue
                    for row in products:
                        item = self.normalize_product_row({name: self.table_value(row, name) for name in row.colnames}, obs)
                        if not str(item.get("productFilename", "")).lower().endswith((".fits", ".fits.gz")):
                            continue
                        name = str(item.get("productFilename", "")).lower()
                        # Keep all FITS products, but tag the enhanced ones so they sort/report clearly.
                        if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
                            item["_enhanced_candidate"] = True
                        key = self.row_identity(item)
                        if key in seen_products:
                            continue
                        seen_products.add(key)
                        product_rows.append(item)

                hla_count = 0
                if telescope_code in ("HST", "BOTH"):
                    try:
                        self.after(0, lambda: self.set_download_progress(operation_id, 84, "Checking Hubble Legacy Archive enhanced products..."))
                        hla_rows = self.fetch_hla_product_rows(target, f"{max(radii):.6f} deg")
                        for item in hla_rows:
                            item["_enhanced_candidate"] = True
                            key = self.row_identity(item)
                            if key not in seen_products:
                                seen_products.add(key)
                                product_rows.append(item)
                                hla_count += 1
                    except Exception as exc:
                        report.append(f"HLA check failed: {exc}")

                product_rows.sort(key=lambda row: (-self.better_source_score(row), self.product_sort_key(row)))
                rgb_sets = self.suggest_rgb_sets_for_rows(product_rows, recipe=self.target_recipe(target))
                enhanced_count = sum(1 for row in product_rows if any(token in str(row.get("productFilename", "")).lower() for token in ENHANCED_PRODUCT_TOKENS) or row.get("_source") == "HLA")
                report.append(f"Products checked: {len(product_rows)} FITS products")
                report.append(f"Better/combined candidates: {enhanced_count}")
                report.append(f"HLA products added: {hla_count}")
                report.append(f"Complete RGB sets found: {len(rgb_sets)}")
                result = (obs_rows, product_rows, "\n".join(report), None)
            except Exception as exc:
                result = ([], [], "", exc)
            self.after(0, lambda: self.finish_better_sources(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def better_source_score(self, row):
        score = self.product_quality_score(row)
        name = str(row.get("productFilename", "")).lower()
        if "_i2d" in name:
            score += 55
        if any(token in name for token in ("_drc", "_drz")):
            score += 45
        if any(token in name for token in ("mosaic", "combined", "coadd")):
            score += 40
        if self.product_rgb_channel(row):
            score += 18
        if self.product_is_direct_fits(row):
            score += 10
        return score

    def finish_better_sources(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        obs_rows, product_rows, report, error = result
        if error:
            self.stop_browser_activity(f"Better source search failed: {self.format_error_message(error)}")
            return
        self.search_results = obs_rows
        self.obs_list.delete(0, "end")
        for row in obs_rows[:500]:
            label = (
                f"{row.get('obs_collection', '')} | {row.get('obs_id', '')} | {row.get('instrument_name', '')} | "
                f"{row.get('filters', '')} | {row.get('t_exptime', '')}s"
            )
            self.obs_list.insert("end", label)
        self.product_results = product_rows
        # Make the more complete sources visible by default.
        self.direct_fits_only_var.set(True)
        self.hide_spectra_var.set(True)
        self.rgb_filters_only_var.set(False)
        self.rgb_sets_only_var.set(False)
        self.refresh_product_list()
        if self.save_search_history_var.get():
            self.save_diagnostic_json(SEARCH_LOG_DIR, f"{self.current_target_for_log()}_better_sources", {
                "target": self.current_target_for_log(),
                "radius": self.radius_var.get(),
                "telescope": self.telescope_var.get(),
                "observation_count": len(obs_rows),
                "product_count": len(product_rows),
                "report": report,
                "observations": obs_rows[:1000],
                "products": product_rows[:2000],
            })
        self.stop_browser_activity(
            f"Better source search found {len(product_rows)} FITS products from {len(obs_rows)} observations. Showing best candidates first."
        )
        messagebox.showinfo("Better / More Complete Sources", report or "Search completed.")

    def completeness_check_async(self):
        target = self.target_var.get().strip()
        rows = list(getattr(self, "product_results", []) or [])
        if not target and not rows:
            messagebox.showinfo("Completeness Check", "Enter a target or run a product search first.")
            return
        operation_id = self.start_browser_activity("Running completeness check...")

        def worker():
            try:
                report = self.build_completeness_report(rows, target)
                result = (report, None)
            except Exception as exc:
                result = ("", exc)
            self.after(0, lambda: self.finish_completeness_check(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def build_completeness_report(self, rows, target):
        rows = list(rows or [])
        channels = {"blue": [], "green": [], "red": []}
        enhanced = []
        hla = []
        for row in rows:
            name = str(row.get("productFilename", "")).lower()
            if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
                enhanced.append(row)
            if row.get("_source") == "HLA":
                hla.append(row)
            channel = self.product_rgb_channel(row)
            if channel:
                channels[channel].append(row)
        rgb_sets = self.suggest_rgb_sets_for_rows(rows, recipe=self.target_recipe(target)) if rows else []
        same_group = bool(rgb_sets and all(id(rgb_sets[0][channel]) in self.rgb_ready_product_ids for channel in ("blue", "green", "red")))
        lines = []
        lines.append(f"Target: {target or '(current product list)'}")
        lines.append(f"Products currently loaded: {len(rows)}")
        lines.append("")
        lines.append("RGB coverage:")
        for channel in ("blue", "green", "red"):
            lines.append(f"- {channel.title()}: {len(channels[channel])} candidate(s)")
        lines.append(f"- Complete RGB sets: {len(rgb_sets)}")
        lines.append(f"- Same observation/alignment group: {'yes' if same_group else 'not confirmed'}")
        lines.append("")
        lines.append("More complete source checks:")
        lines.append(f"- Mosaic/drizzled/i2d/combined candidates: {len(enhanced)}")
        lines.append(f"- HLA/Hubble enhanced products currently loaded: {len(hla)}")
        lines.append(f"- Larger/wider nearby observations loaded: {'yes' if len(getattr(self, 'search_results', []) or []) > 1 else 'not confirmed'}")
        if hasattr(self, "presentation_cleanup_fills"):
            lines.append(f"- Presentation cleanup filled internal dark gaps: {self.presentation_cleanup_fills}")
        else:
            lines.append("- Gap/border cleanup: compose an RGB image first for an image-level check")
        lines.append("")
        if not rows:
            lines.append("Recommendation: run Find Better / More Complete Image Sources first.")
        elif rgb_sets and enhanced:
            lines.append("Recommendation: use the best suggested RGB set and prefer the enhanced candidates near the top of the product list.")
        elif rgb_sets:
            lines.append("Recommendation: you have RGB coverage, but should run Find Better / More Complete Image Sources to look for mosaics/drizzled/i2d products.")
        else:
            lines.append("Recommendation: run Find Better / More Complete Image Sources with a wider radius; NASA-style images often combine multiple visits or products.")
        return "\n".join(lines)

    def finish_completeness_check(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        report, error = result
        if error:
            self.stop_browser_activity(f"Completeness check failed: {self.format_error_message(error)}")
            return
        self.save_diagnostic_json(SEARCH_LOG_DIR, f"{self.current_target_for_log()}_completeness_check", {
            "target": self.current_target_for_log(),
            "report": report,
            "loaded_products": len(getattr(self, "product_results", []) or []),
        })
        self.stop_browser_activity("Completeness check finished.")
        messagebox.showinfo("Completeness Check", report)

    def products_async(self):
        if not self.require_astroquery():
            return
        selection = self.obs_list.curselection()
        if not selection:
            messagebox.showinfo("Products", "Select an observation first, or use Get All Products to scan the observation list.")
            return
        obs = self.search_results[selection[0]]
        obsid = obs.get("obsid")
        operation_id = self.start_browser_activity("Loading products for selected observation...")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                products = OBSERVATIONS.get_product_list(obsid)
                rows = [self.normalize_product_row({name: self.table_value(row, name) for name in row.colnames}, obs) for row in products]
                rows = [
                    item for item in rows
                    if str(item.get("productFilename", "")).lower().endswith((".fits", ".fits.gz"))
                ]
                rows.sort(key=self.product_sort_key)
                result = (rows, None)
            except Exception as exc:
                result = ([], exc)
            self.after(0, lambda: self.finish_products(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def products_all_async(self):
        if not self.require_astroquery():
            return
        if not self.search_results:
            messagebox.showinfo("Get All Products", "Search MAST first so there are observations to scan.")
            return
        rows_to_scan = self.search_results[:60]
        self.browser_timeout_seconds = 1800
        operation_id = self.start_browser_activity(f"Loading products from {len(rows_to_scan)} observations...")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                all_rows = []
                seen = set()
                total = len(rows_to_scan)
                for index, obs in enumerate(rows_to_scan, start=1):
                    obsid = obs.get("obsid")
                    obs_label = obs.get("obs_id") or obsid or f"observation {index}"
                    self.after(
                        0,
                        lambda i=index, t=total, label=obs_label: self.set_download_progress(
                            operation_id,
                            min(95, i / max(1, t) * 95),
                            f"Loading products {i} of {t}: {label}",
                        ),
                    )
                    if not obsid:
                        continue
                    try:
                        products = OBSERVATIONS.get_product_list(obsid)
                    except Exception:
                        continue
                    for row in products:
                        item = self.normalize_product_row({name: self.table_value(row, name) for name in row.colnames}, obs)
                        if not str(item.get("productFilename", "")).lower().endswith((".fits", ".fits.gz")):
                            continue
                        key = self.row_identity(item)
                        if key in seen:
                            continue
                        seen.add(key)
                        all_rows.append(item)
                all_rows.sort(key=self.product_sort_key)
                result = (all_rows, None)
            except Exception as exc:
                result = ([], exc)
            self.after(0, lambda: self.finish_products(operation_id, result, all_observations=True))

        self.reset_download_progress()
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def normalize_product_row(row, obs):
        row = dict(row)
        for key in ("obs_collection", "instrument_name", "target_name", "filters", "obs_id"):
            if not row.get(key) and obs.get(key):
                row[key] = obs.get(key)
        if row.get("obs_collection"):
            row.setdefault("mission", row.get("obs_collection"))
        if not row.get("Spectral_Elt") and row.get("filters"):
            row["Spectral_Elt"] = row.get("filters")
        if not row.get("Detector") and row.get("instrument_name"):
            row["Detector"] = row.get("instrument_name")
        if not row.get("Target") and row.get("target_name"):
            row["Target"] = row.get("target_name")
        return row

    @staticmethod
    def product_sort_key(item):
        name = str(item.get("productFilename", "")).lower()
        priority = 5
        for index, token in enumerate(("i2d", "drc", "drz", "mosaic", "combined", "coadd", "cal", "rate", "flc", "flt", "uncal", "raw")):
            if f"_{token}." in name or name.endswith(f"{token}.fits"):
                priority = index
                break
        try:
            size = -int(float(item.get("size", 0) or 0))
        except Exception:
            size = 0
        return priority, size, name

    def finish_products(self, operation_id, result, all_observations=False):
        if operation_id != self.browser_operation_id:
            return
        rows, error = result
        if error:
            self.stop_browser_activity(f"Product lookup failed: {error}")
            return
        self.product_results = rows
        self.refresh_product_list()
        if all_observations:
            self.rgb_sets_only_var.set(False)
            self.refresh_product_list()
        if self.save_product_lists_var.get():
            self.save_diagnostic_json(PRODUCT_LOG_DIR, f"{self.current_target_for_log()}_products", {
                "target": self.current_target_for_log(),
                "telescope": self.telescope_var.get(),
                "all_observations": bool(all_observations),
                "product_count": len(rows),
                "visible_count": len(self.visible_product_results),
                "products": rows[:5000],
            })
        self.stop_browser_activity(
            f"Found {len(rows)} FITS products{' across observations' if all_observations else ''}. Showing {len(self.visible_product_results)} with the current filters."
        )

    def download_selected_async(self):
        selections = self.product_list.curselection()
        if not selections:
            messagebox.showinfo("Download", "Select one or more products.")
            return
        rows = [self.visible_product_results[index] for index in selections]
        self.download_product_rows_async(rows)

    def download_product_rows_async(self, rows, folder_label=None, rgb_set=None):
        if not (rows and rows[0].get("_source") == "HLA") and not self.require_astroquery():
            return
        target = self.target_var.get().strip().replace(" ", "_") or "target"
        if folder_label:
            target = f"{target}_{folder_label}"
        download_path = DOWNLOAD_DIR / target / datetime.now().strftime("%Y%m%d_%H%M%S")
        download_path.mkdir(parents=True, exist_ok=True)
        self.browser_timeout_seconds = 3600
        operation_id = self.start_browser_activity(f"Downloading {len(rows)} product(s)...")
        self.reset_download_progress()
        heartbeat_active = {"running": True}

        def download_heartbeat(started):
            if operation_id != self.browser_operation_id or not heartbeat_active["running"]:
                return
            elapsed = int((datetime.now() - started).total_seconds())
            minutes, seconds = divmod(elapsed, 60)
            self.set_download_progress(
                operation_id,
                10,
                f"MAST download is still running ({minutes}:{seconds:02d}). Large FITS files can take a while.",
            )
            self.after(15000, lambda: download_heartbeat(started))

        self.after(15000, lambda: download_heartbeat(datetime.now()))

        def worker():
            try:
                if rows and rows[0].get("_source") == "HLA":
                    manifest = self.download_hla_products(rows, download_path, operation_id)
                else:
                    self.after(
                        0,
                        lambda: self.set_download_progress(
                            operation_id,
                            5,
                            "MAST download is running. The archive reports progress only after the selected files finish.",
                        ),
                    )
                    try:
                        manifest = OBSERVATIONS.download_products(rows, download_dir=str(download_path), cache=True)
                    except Exception as exc:
                        self.after(
                            0,
                            lambda: self.set_download_progress(
                                operation_id,
                                5,
                                "Bulk MAST download did not start cleanly. Trying the selected files one at a time...",
                            ),
                        )
                        manifest = self.download_mast_products_individually(rows, download_path, operation_id, exc)
                result = (manifest, download_path, None, rgb_set)
            except Exception as exc:
                result = (None, download_path, exc, rgb_set)
            heartbeat_active["running"] = False
            self.after(0, lambda: self.finish_download(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def format_error_message(error):
        text = str(error).strip()
        if text and text.lower() != "true":
            return text
        return repr(error)

    @staticmethod
    def safe_filename(name):
        cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(name))
        return cleaned.strip("._") or "hla_product.fits"

    def download_hla_products(self, rows, download_path, operation_id):
        downloaded = []
        total_files = max(1, len(rows))
        for index, row in enumerate(rows, start=1):
            url = html.unescape(str(row.get("URL", "")))
            filename = self.safe_filename(row.get("productFilename", "hla_product.fits"))
            output_path = download_path / filename
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    ((i - 1) / total) * 100,
                    f"Downloading file {i} of {total}: {name}",
                ),
            )

            def reporthook(block_count, block_size, total_size, i=index, total=total_files, name=filename):
                if total_size and total_size > 0:
                    file_fraction = min(1.0, (block_count * block_size) / total_size)
                    percent = (((i - 1) + file_fraction) / total) * 100
                    detail = f"Downloading file {i} of {total}: {name} ({int(file_fraction * 100)}%)"
                else:
                    percent = ((i - 1) / total) * 100
                    detail = f"Downloading file {i} of {total}: {name}"
                self.after(0, lambda p=percent, d=detail: self.set_download_progress(operation_id, p, d))

            urllib.request.urlretrieve(url, output_path, reporthook=reporthook)
            downloaded.append(str(output_path))
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    (i / total) * 100,
                    f"Finished file {i} of {total}: {name}",
                ),
            )
        return downloaded

    def finish_download(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        manifest, download_path, error, rgb_set = result
        if error:
            self.stop_browser_activity(f"Download failed: {self.format_error_message(error)}")
            return
        self.download_progress_var.set(100)
        self.download_detail.set("Download complete.")
        if self.save_download_logs_var.get():
            self.save_diagnostic_json(DOWNLOAD_LOG_DIR, f"{self.current_target_for_log()}_download", {
                "target": self.current_target_for_log(),
                "download_path": str(download_path),
                "manifest": manifest,
                "rgb_set": rgb_set,
            })
        if rgb_set:
            self.load_downloaded_rgb_set(manifest, download_path, rgb_set)
            return
        self.stop_browser_activity(f"Downloaded products to {download_path}")

    def load_downloaded_rgb_set(self, manifest, download_path, rgb_set):
        downloaded = self.extract_downloaded_paths(manifest, download_path)
        channel_paths = self.match_downloaded_rgb_paths(downloaded, rgb_set)
        missing = [channel for channel in ("blue", "green", "red") if channel not in channel_paths]
        if missing:
            self.stop_browser_activity(
                f"Downloaded RGB products to {download_path}, but could not identify: {', '.join(missing)}. "
                "Use Load Latest RGB Set or choose the files manually."
            )
            return
        self.red_path_var.set(str(channel_paths["red"]))
        self.green_path_var.set(str(channel_paths["green"]))
        self.blue_path_var.set(str(channel_paths["blue"]))
        self.compose_status.set(f"Loading downloaded RGB channels from {download_path.name}...")
        self.notebook.select(self.compose_tab)
        self.compose_progress.start(12)
        self.preview_channel_thumbnails_async(channel_paths, download_path)
        self.stop_browser_activity(f"Downloaded and loaded RGB set from {download_path}")

    def download_mast_products_individually(self, rows, download_path, operation_id, first_error=None):
        downloaded = []
        total_files = max(1, len(rows))
        for index, row in enumerate(rows, start=1):
            data_uri = str(row.get("dataURI", "") or row.get("dataURL", "")).strip()
            if not data_uri:
                raise RuntimeError(
                    f"Bulk download failed ({self.format_error_message(first_error)}), "
                    f"and {row.get('productFilename', 'one selected product')} has no MAST download URI."
                )
            filename = self.safe_filename(row.get("productFilename", Path(data_uri).name or f"mast_product_{index}.fits"))
            output_path = download_path / filename
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    ((i - 1) / total) * 100,
                    f"Downloading file {i} of {total}: {name}",
                ),
            )
            OBSERVATIONS.download_file(data_uri, local_path=str(output_path), cache=True)
            downloaded.append(str(output_path))
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    (i / total) * 100,
                    f"Finished file {i} of {total}: {name}",
                ),
            )
        return downloaded

    @staticmethod
    def extract_downloaded_paths(manifest, download_path):
        paths = []
        try:
            if hasattr(manifest, "colnames") and "Local Path" in manifest.colnames:
                paths.extend(Path(str(item)) for item in manifest["Local Path"])
            elif isinstance(manifest, (list, tuple)):
                paths.extend(Path(str(item)) for item in manifest)
        except Exception:
            pass
        paths = [path for path in paths if path.exists()]
        if not paths:
            paths = [
                path for path in Path(download_path).rglob("*")
                if path.is_file() and path.name.lower().endswith((".fits", ".fits.gz", ".fit"))
            ]
        return paths

    def match_downloaded_rgb_paths(self, downloaded_paths, rgb_set):
        matched = {}
        for channel, row in rgb_set.items():
            expected = str(row.get("productFilename", "")).lower()
            for path in downloaded_paths:
                if path.name.lower() == expected or path.name.lower().endswith(expected):
                    matched[channel] = path
                    break
        if len(matched) < 3:
            fallback = self.pick_rgb_files_from_paths(downloaded_paths)
            matched.update({channel: path for channel, path in fallback.items() if channel not in matched})
        return matched

    def pick_rgb_files_from_paths(self, files):
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

    def show_image_on_canvas(self, canvas, image, attr_name, zoom=1.0):
        canvas.delete("all")
        width = max(320, canvas.winfo_width())
        height = max(240, canvas.winfo_height())
        preview = image.copy()
        if zoom <= 1.01:
            preview.thumbnail((width, height), Image.Resampling.LANCZOS)
        else:
            base = image.copy()
            base.thumbnail((width, height), Image.Resampling.LANCZOS)
            size = (max(1, int(base.width * zoom)), max(1, int(base.height * zoom)))
            preview = base.resize(size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(preview)
        setattr(self, attr_name, photo)
        canvas.create_image(width / 2, height / 2, image=photo, anchor="center")

    def open_folder(self, folder):
        folder.mkdir(exist_ok=True)
        try:
            import os
            os.startfile(str(folder))
        except Exception:
            messagebox.showinfo("Folder", str(folder))

    def on_close(self):
        if self.browser_busy_job:
            try:
                self.after_cancel(self.browser_busy_job)
            except Exception:
                pass
            self.browser_busy_job = None
        if hasattr(self, "compose_progress"):
            try:
                self.compose_progress.stop()
            except Exception:
                pass
        SETTINGS["geometry"] = self.geometry()
        if hasattr(self, "auto_compose_var"):
            SETTINGS["auto_compose_after_load"] = bool(self.auto_compose_var.get())
        if hasattr(self, "composite_size_var"):
            SETTINGS["composite_size"] = self.composite_size_var.get()
        if hasattr(self, "save_quality_settings"):
            self.save_quality_settings()
        save_settings(SETTINGS)
        self.destroy()



def instrument_debug_methods():
    """Wrap selected high-value methods with logging without cluttering the UI code."""
    method_names = [
        "__init__",
        "setup_style",
        "build_ui",
        "build_setup_tab",
        "build_browser_tab",
        "build_convert_tab",
        "build_compose_tab",
        "refresh_dependency_status",
        "search_async",
        "hla_search_async",
        "products_async",
        "products_all_async",
        "download_selected_async",
        "preview_fits_async",
        "compose_async",
        "load_latest_rgb_set",
        "save_preview_outputs",
        "save_composite_outputs",
        "open_latest_output",
        "save_project_file",
        "open_project_file",
        "better_sources_async",
        "completeness_check_async",
        "finish_search",
        "finish_products",
        "finish_better_sources",
        "finish_completeness_check",
        "finish_download",
        "on_close",
    ]
    for name in method_names:
        func = getattr(HubbleWorkbench, name, None)
        if callable(func) and not getattr(func, "_debug_wrapped", False):
            wrapped = debug_call(func)
            wrapped._debug_wrapped = True
            setattr(HubbleWorkbench, name, wrapped)



def center_and_raise_startup_window(app):
    """Make the Tk window visible even when saved geometry is off-screen or behind other windows."""
    try:
        info_log("Forcing startup window visibility")
        app.update_idletasks()

        screen_w = int(app.winfo_screenwidth())
        screen_h = int(app.winfo_screenheight())
        current_geometry = app.geometry()
        info_log(f"Screen size: {screen_w}x{screen_h}")
        info_log(f"Current window geometry before visibility fix: {current_geometry}")

        # Saved Tk geometry can sometimes put the app off-screen after monitor changes.
        # Use a safe centered geometry every time during debug startup.
        width = min(1160, max(940, screen_w - 120))
        height = min(760, max(620, screen_h - 120))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        safe_geometry = f"{width}x{height}+{x}+{y}"
        app.geometry(safe_geometry)
        info_log(f"Applied safe centered geometry: {safe_geometry}")

        app.deiconify()
        app.lift()
        app.focus_force()
        app.attributes("-topmost", True)
        app.after(1500, lambda: app.attributes("-topmost", False))
        app.after(200, lambda: info_log(f"Window state after startup: state={app.state()}, geometry={app.geometry()}, viewable={app.winfo_viewable()}"))
        app.after(500, lambda: app.browser_status.set("Debug startup complete. Window is visible and mainloop is running."))
    except Exception:
        log_exception("Unable to force startup window visibility")

def run_app():
    info_log("Starting run_app()")
    instrument_debug_methods()
    try:
        app = HubbleWorkbench()
        center_and_raise_startup_window(app)
        info_log("Entering Tk mainloop")
        app.mainloop()
        info_log("Tk mainloop exited normally")
    except Exception:
        log_exception("Fatal error while starting or running Hubble Workbench")
        try:
            messagebox.showerror(
                "Hubble Workbench startup error",
                f"The app hit an error. Details were written to:\n{DEBUG_LOG_PATH}",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    run_app()

