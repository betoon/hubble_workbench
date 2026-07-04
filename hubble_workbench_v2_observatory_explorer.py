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
import shutil
import subprocess
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
from PIL import Image

# Disable the decompression bomb protection entirely

Image.MAX_IMAGE_PIXELS = None



from hubble_workbench_app.paths import (
    APP_DIR,
    DOWNLOAD_DIR,
    OUTPUT_DIR,
    NOTES_DIR,
    SETTINGS_PATH,
    MESSIER_LIST_PATH,
    RGB_WORKING_PREVIEW_MAX_PIXELS,
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
from hubble_workbench_app.settings import SETTINGS, save_settings
from hubble_workbench_app.fits_io import (
    FITS,
    OBSERVATIONS,
    MISSING_DEPS,
    configure_logging as configure_fits_logging,
    first_image_hdu,
)
from hubble_workbench_app.image_processing import (
    normalize_image,
    downsample_array_for_preview,
    float_rgb_to_uint8,
    float_rgb_to_uint16,
    patch_sample_color,
    blended_gap_image,
    crop_black_border,
)
from hubble_workbench_app.hla_workflow import HlaWorkflowMixin
from hubble_workbench_app.app_utilities import AppUtilitiesMixin
from hubble_workbench_app.quality_settings import QualitySettingsMixin
from hubble_workbench_app.target_gallery import TargetGalleryMixin
from hubble_workbench_app.dependency_status import DependencyStatusMixin
from hubble_workbench_app.browser_activity import BrowserActivityMixin
from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin
from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin
from hubble_workbench_app.project_workflow import ProjectWorkflowMixin
from hubble_workbench_app.preview_workflow import PreviewWorkflowMixin
from hubble_workbench_app.download_workflow import DownloadWorkflowMixin
from hubble_workbench_app.product_scoring import ProductScoringMixin
from hubble_workbench_app.mast_helpers import MastSearchHelperMixin
from hubble_workbench_app.catalogs import (
    TARGET_GALLERY,
    JWST_TARGET_GALLERY,
    TELESCOPE_CHOICES,
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
configure_fits_logging(debug_log, info_log, warning_log)
install_global_exception_logging()
atexit.register(log_shutdown)
# ---------------------------------------------------



class HubbleWorkbench(HlaWorkflowMixin, AppUtilitiesMixin, QualitySettingsMixin, TargetGalleryMixin, DependencyStatusMixin, BrowserActivityMixin, ObservatoryWorkflowMixin, ComposeWorkflowMixin, ProjectWorkflowMixin, PreviewWorkflowMixin, DownloadWorkflowMixin, ProductScoringMixin, MastSearchHelperMixin, tk.Tk):
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

    def observatory_analyze_current(self):
        return super().observatory_analyze_current()

    def observatory_draw_current_mosaic(self):
        return super().observatory_draw_current_mosaic()

    def observatory_search_wider_async(self):
        return super().observatory_search_wider_async()

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
        return super().on_quality_option_changed()

    def on_stretch_setting_changed(self, _event=None):
        return super().on_stretch_setting_changed(_event)

    def reset_advanced_stretch(self):
        return super().reset_advanced_stretch()

    def save_quality_settings(self):
        return super().save_quality_settings()

    def refresh_dependency_status(self):
        return super().refresh_dependency_status()

    def on_telescope_changed(self, _event=None):
        SETTINGS["telescope"] = self.telescope_var.get()
        save_settings(SETTINGS)
        gallery = self.current_gallery()
        self.target_gallery_combo.configure(values=[item[0] for item in gallery])
        self.target_gallery_var.set(gallery[0][0])
        self.browser_status.set(f"Using {self.telescope_var.get()} searches.")

    def use_target_gallery(self):
        return super().use_target_gallery()

    def search_target_gallery_hla(self):
        return super().search_target_gallery_hla()

    def cancel_browser_activity(self, message=None):
        return super().cancel_browser_activity(message)

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
        return super().hla_search_async(fallback_message)

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
        return super().download_selected_async()

    def choose_convert_file(self):
        return super().choose_convert_file()

    def preview_fits_async(self):
        return super().preview_fits_async()

    def save_preview_outputs(self):
        return super().save_preview_outputs()

    def choose_channel(self, var):
        return super().choose_channel(var)

    def load_latest_rgb_set(self):
        return super().load_latest_rgb_set()
    def compose_async(self):
        return super().compose_async()

    def on_tuning_changed(self, _value=None):
        return super().on_tuning_changed(_value)

    def reset_straighten(self):
        return super().reset_straighten()

    def apply_image_tuning(self):
        return super().apply_image_tuning()

    def update_rgb_preview(self):
        return super().update_rgb_preview()

    def apply_preset_preview(self, name):
        return super().apply_preset_preview(name)

    def apply_processing_preset(self, name, update_status=True):
        return super().apply_processing_preset(name, update_status)
    def save_composite_outputs(self):
        return super().save_composite_outputs()

    def open_latest_output(self):
        return super().open_latest_output()

    def save_project_file(self):
        return super().save_project_file()

    def open_project_file(self):
        return super().open_project_file()

    def show_image_on_canvas(self, canvas, image, attr_name, zoom=1.0):
        return super().show_image_on_canvas(canvas, image, attr_name, zoom)

    def open_folder(self, folder):
        return super().open_folder(folder)

    def open_file(self, path):
        return super().open_file(path)

    def on_close(self):
        return super().on_close()

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

