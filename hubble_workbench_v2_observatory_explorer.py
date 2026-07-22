import math
import atexit
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

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
from hubble_workbench_app.app_logging import (
    debug_call,
    debug_log,
    info_log,
    install_global_exception_logging,
    log_environment_paths,
    log_exception,
    log_shutdown,
    setup_debug_logging,
    warning_log,
)
from hubble_workbench_app.developer_tools import DeveloperToolsMixin
from hubble_workbench_app.debug_console import DebugConsoleMixin
from hubble_workbench_app.better_sources import BetterSourcesMixin
from hubble_workbench_app.product_browser import ProductBrowserMixin
from hubble_workbench_app.search_workflow import SearchWorkflowMixin
from hubble_workbench_app.hla_workflow import HlaWorkflowMixin
from hubble_workbench_app.app_utilities import AppUtilitiesMixin
from hubble_workbench_app.quality_settings import QualitySettingsMixin
from hubble_workbench_app.target_gallery import TargetGalleryMixin
from hubble_workbench_app.dependency_status import DependencyStatusMixin
from hubble_workbench_app.browser_activity import BrowserActivityMixin
from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin
from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin
from hubble_workbench_app.hydrogen_workflow import HydrogenWorkflowMixin
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


setup_debug_logging(__file__)
configure_fits_logging(debug_log, info_log, warning_log)
install_global_exception_logging()
atexit.register(log_shutdown)# ---------------------------------------------------



class HubbleWorkbench(DebugConsoleMixin, DeveloperToolsMixin, BetterSourcesMixin, ProductBrowserMixin, SearchWorkflowMixin, HlaWorkflowMixin, AppUtilitiesMixin, QualitySettingsMixin, TargetGalleryMixin, DependencyStatusMixin, BrowserActivityMixin, ObservatoryWorkflowMixin, ComposeWorkflowMixin, HydrogenWorkflowMixin, ProjectWorkflowMixin, PreviewWorkflowMixin, DownloadWorkflowMixin, ProductScoringMixin, MastSearchHelperMixin, tk.Tk):
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

    def save_developer_settings(self):
        return super().save_developer_settings()

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
        self.hydrogen_tab = ttk.Frame(self.notebook, padding=12)
        self.debug_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.setup_tab, text="Setup")
        self.notebook.add(self.browser_tab, text="MAST Browser")
        self.notebook.add(self.observatory_tab, text="Observatory Explorer")
        self.notebook.add(self.convert_tab, text="FITS Preview / Convert")
        self.notebook.add(self.compose_tab, text="Color Composer")
        self.notebook.add(self.hydrogen_tab, text="Hydrogen Enhance")
        self.notebook.add(self.debug_tab, text="Debug Console")

        self.build_setup_tab()
        self.build_browser_tab()
        self.build_observatory_tab()
        self.build_convert_tab()
        self.build_compose_tab()
        self.build_hydrogen_tab()
        self.build_debug_console_tab()

    def build_setup_tab(self):
        setup_content = self.build_scrollable_tab_content(self.setup_tab)
        ttk.Label(setup_content, text="Space Telescope Workbench", style="Title.TLabel").pack(anchor="w")
        self.dep_text = tk.Text(
            setup_content,
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
        buttons = ttk.Frame(setup_content)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Refresh Status", command=self.refresh_dependency_status).pack(side="left")
        ttk.Button(buttons, text="Open Downloads Folder", command=lambda: self.open_folder(DOWNLOAD_DIR)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Open Outputs Folder", command=lambda: self.open_folder(OUTPUT_DIR)).pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Open Observatory Test Guide",
            command=lambda: self.open_file(APP_DIR / "OBSERVATORY_EXPLORER_TEST_GUIDE.md"),
        ).pack(side="left", padx=(8, 0))

    def build_scrollable_tab_content(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        vertical = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        content = ttk.Frame(canvas, padding=(0, 0, 4, 4))
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def keep_minimum_width(event):
            requested_width = max(content.winfo_reqwidth(), event.width)
            canvas.itemconfigure(window_id, width=requested_width)
            update_scroll_region()

        def on_mousewheel(event):
            if event.state & 0x0001:
                canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", keep_minimum_width)
        canvas.bind("<MouseWheel>", on_mousewheel)
        content.bind("<MouseWheel>", on_mousewheel)
        return content

    def build_browser_tab(self):
        browser_content = self.build_scrollable_tab_content(self.browser_tab)
        gallery = ttk.Frame(browser_content)
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

        top = ttk.Frame(browser_content)
        top.pack(fill="x")
        top_target_row = ttk.Frame(top)
        top_target_row.pack(fill="x")
        top_action_row = ttk.Frame(top)
        top_action_row.pack(fill="x", pady=(4, 0))
        top_secondary_row = ttk.Frame(top)
        top_secondary_row.pack(fill="x", pady=(4, 0))
        ttk.Label(top_target_row, text="Target").pack(side="left")
        self.target_var = tk.StringVar(value=SETTINGS.get("last_target", "M51"))
        ttk.Entry(top_target_row, textvariable=self.target_var, width=28).pack(side="left", padx=(6, 8))
        ttk.Label(top_target_row, text="Radius").pack(side="left")
        self.radius_var = tk.StringVar(value=SETTINGS.get("radius", "0.05 deg"))
        ttk.Entry(top_target_row, textvariable=self.radius_var, width=10).pack(side="left", padx=(6, 8))
        self.search_button = ttk.Button(top_action_row, text="Search MAST", command=self.search_async, style="Accent.TButton")
        self.search_button.pack(side="left")
        self.easy_button = ttk.Button(top_action_row, text="Easy RGB Image", command=self.easy_rgb_async, style="Accent.TButton")
        self.easy_button.pack(side="left", padx=(8, 0))
        self.easy_hq_button = ttk.Button(top_action_row, text="Easy High Quality", command=self.easy_high_quality_async, style="Accent.TButton")
        self.easy_hq_button.pack(side="left", padx=(8, 0))
        self.easy_all_sensors_button = ttk.Button(top_action_row, text="Easy All Sensors", command=self.easy_all_sensors_async, style="Accent.TButton")
        self.easy_all_sensors_button.pack(side="left", padx=(8, 0))
        self.hla_button = ttk.Button(top_secondary_row, text="Search HLA Fallback", command=self.hla_search_async)
        self.hla_button.pack(side="left")
        self.products_button = ttk.Button(top_secondary_row, text="Get Products", command=self.products_async)
        self.products_button.pack(side="left", padx=(8, 0))
        self.all_products_button = ttk.Button(top_secondary_row, text="Get All Products", command=self.products_all_async)
        self.all_products_button.pack(side="left", padx=(8, 0))
        self.download_button = ttk.Button(top_secondary_row, text="Download Selected Products", command=self.download_selected_async)
        self.download_button.pack(side="left", padx=(8, 0))
        self.stop_browser_button = ttk.Button(top_secondary_row, text="Stop", command=self.cancel_browser_activity, state="disabled")
        self.stop_browser_button.pack(side="left", padx=(8, 0))

        self.easy_all_sensors_status_var = tk.StringVar(value="Easy All Sensors: ready.")
        ttk.Label(browser_content, textvariable=self.easy_all_sensors_status_var, wraplength=1040).pack(anchor="w", pady=(4, 0))

        source_tools = ttk.Frame(browser_content)
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

        panes = ttk.PanedWindow(browser_content, orient="horizontal")
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
        rgb_actions_second = ttk.Frame(rgb_tab)
        rgb_actions_second.pack(fill="x", pady=(4, 0))
        ttk.Button(rgb_actions, text="Use Best Set", command=self.use_best_rgb_set, style="Accent.TButton").pack(side="left")
        ttk.Button(rgb_actions, text="Use Suggested Set", command=self.use_suggested_rgb_set).pack(side="left")
        ttk.Button(rgb_actions_second, text="Pick Best Available Channels", command=self.pick_best_available_rgb_channels).pack(side="left")
        ttk.Button(rgb_actions_second, text="Download Selected RGB Channels", command=self.download_rgb_candidates_async).pack(side="left", padx=(8, 0))
        ttk.Button(rgb_actions_second, text="Copy RGB Picks", command=self.copy_rgb_candidates).pack(side="left", padx=(8, 0))

        easy_rgb_actions = ttk.LabelFrame(rgb_tab, text="Easy All Sensors")
        easy_rgb_actions.pack(fill="x", pady=(8, 0))
        easy_rgb_run_row = ttk.Frame(easy_rgb_actions)
        easy_rgb_run_row.pack(fill="x", padx=8, pady=(6, 0))
        easy_rgb_summary_row = ttk.Frame(easy_rgb_actions)
        easy_rgb_summary_row.pack(fill="x", padx=8, pady=(4, 0))
        easy_rgb_output_row = ttk.Frame(easy_rgb_actions)
        easy_rgb_output_row.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Button(easy_rgb_run_row, text="Download Easy RGB", command=self.download_easy_all_sensors_rgb_async, style="Accent.TButton").pack(side="left")
        ttk.Button(easy_rgb_summary_row, text="Save Summary", command=self.save_easy_all_sensors_summary).pack(side="left")
        ttk.Button(easy_rgb_summary_row, text="Copy Summary", command=self.copy_easy_all_sensors_summary).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_summary_row, text="Open Latest", command=self.open_latest_easy_all_sensors_summary).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_summary_row, text="Open Folder", command=self.open_easy_all_sensors_summary_folder).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_summary_row, text="Run Index", command=self.open_easy_all_sensors_run_index).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_summary_row, text="Copy Latest Run", command=self.copy_latest_easy_all_sensors_run).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_summary_row, text="Copy Run ID", command=self.copy_latest_easy_all_sensors_run_id).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_output_row, text="Open Preview", command=self.open_latest_easy_all_sensors_preview).pack(side="left")
        ttk.Button(easy_rgb_output_row, text="Copy Preview Path", command=self.copy_latest_easy_all_sensors_preview_path).pack(side="left", padx=(8, 0))
        ttk.Button(easy_rgb_output_row, text="Open Run Folder", command=self.open_latest_easy_all_sensors_run_folder).pack(side="left", padx=(8, 0))
        ttk.Label(
            easy_rgb_actions,
            text="Download loads and auto-composes the Easy All Sensors picks. Summaries save the selected channels and alignment guidance.",
            wraplength=920,
        ).pack(anchor="w", padx=8, pady=(4, 6))

        self.browser_status = tk.StringVar(value="")
        self.browser_progress = ttk.Progressbar(browser_content, mode="indeterminate")
        self.browser_progress.pack(fill="x", pady=(8, 0))
        self.download_progress_var = tk.DoubleVar(value=0)
        self.download_progress = ttk.Progressbar(
            browser_content,
            mode="determinate",
            variable=self.download_progress_var,
            maximum=100,
        )
        self.download_progress.pack(fill="x", pady=(6, 0))
        self.download_detail = tk.StringVar(value="")
        ttk.Label(browser_content, textvariable=self.download_detail).pack(anchor="w", pady=(4, 0))
        ttk.Label(browser_content, textvariable=self.browser_status).pack(anchor="w", pady=(6, 0))

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


    def build_observatory_scroll_area(self):
        return self.build_scrollable_tab_content(self.observatory_tab)

    def build_observatory_tab(self):
        """Version 2.0 foundation: multi-observatory overview and sky mosaic coverage."""
        observatory_content = self.build_observatory_scroll_area()
        ttk.Label(observatory_content, text="Observatory Explorer 3.0", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            observatory_content,
            text=(
                "Explore the target across Hubble/JWST observations, check filter coverage, "
                "and draw a first-pass sky mosaic map from MAST observation coordinates."
            ),
            wraplength=1050,
        ).pack(anchor="w", pady=(4, 10))

        controls = ttk.Frame(observatory_content)
        controls.pack(fill="x", pady=(0, 8))
        controls_primary = ttk.Frame(controls)
        controls_primary.pack(fill="x")
        controls_secondary = ttk.Frame(controls)
        controls_secondary.pack(fill="x", pady=(4, 0))
        ttk.Button(controls_primary, text="Analyze Current Search", command=self.observatory_analyze_current, style="Accent.TButton").pack(side="left")
        ttk.Button(controls_primary, text="Build Sky Mosaic View", command=self.observatory_draw_current_mosaic).pack(side="left", padx=(8, 0))
        ttk.Button(controls_primary, text="Prepare Best RGB Layer", command=self.observatory_prepare_best_rgb_layer, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(controls_primary, text="Composition Strategy", command=self.observatory_show_composition_strategy, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(controls_secondary, text="Search Wider Radius", command=self.observatory_search_wider_async).pack(side="left")
        ttk.Button(controls_secondary, text="Find Better Sources", command=self.better_sources_async).pack(side="left", padx=(8, 0))
        ttk.Button(controls_secondary, text="Completeness Check", command=self.completeness_check_async).pack(side="left", padx=(8, 0))
        ttk.Button(controls_secondary, text="Image Readiness", command=self.observatory_show_composition_readiness).pack(side="left", padx=(8, 0))

        sensor_panel = ttk.LabelFrame(observatory_content, text="Sensor / Instrument Coverage", padding=8)
        sensor_panel.pack(fill="x", pady=(0, 8))
        sensor_tools = ttk.Frame(sensor_panel)
        sensor_tools.pack(fill="x")
        sensor_filter_row = ttk.Frame(sensor_tools)
        sensor_filter_row.pack(fill="x")
        sensor_primary_row = ttk.Frame(sensor_tools)
        sensor_primary_row.pack(fill="x", pady=(4, 0))
        sensor_secondary_row = ttk.Frame(sensor_tools)
        sensor_secondary_row.pack(fill="x", pady=(4, 0))
        ttk.Label(sensor_filter_row, text="Sensor filter").pack(side="left")
        self.sensor_filter_var = tk.StringVar(value="All sensors")
        sensor_names = ["All sensors", "Hubble only", "JWST only", "WFC3 UVIS", "WFC3 IR", "ACS WFC", "WFPC2", "NICMOS", "NIRCam", "MIRI", "Other Hubble", "Other JWST", "Unknown sensor"]
        self.sensor_filter_combo = ttk.Combobox(
            sensor_filter_row,
            textvariable=self.sensor_filter_var,
            values=sensor_names,
            state="readonly",
            width=18,
        )
        self.sensor_filter_combo.pack(side="left", padx=(8, 0))
        self.sensor_filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.observatory_sensor_filter_changed())
        ttk.Button(sensor_filter_row, text="Search Selected Sensor", command=self.search_selected_sensor_async, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(sensor_filter_row, text="Refresh Sensors", command=self.observatory_update_sensor_dashboard).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_primary_row, text="Sensor Report", command=self.observatory_show_sensor_report, style="Accent.TButton").pack(side="left")
        ttk.Button(sensor_primary_row, text="Rank Sensors", command=self.observatory_show_sensor_readiness).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_primary_row, text="Use Best Sensor", command=self.observatory_use_best_sensor).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_primary_row, text="Sensor RGB Plan", command=self.observatory_show_sensor_rgb_plan).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_primary_row, text="Mixed RGB Plan", command=self.observatory_show_cross_sensor_rgb_plan).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_primary_row, text="Prepare Sensor RGB", command=self.observatory_prepare_sensor_rgb_layer, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(sensor_primary_row, text="Prepare Mixed RGB", command=self.observatory_prepare_cross_sensor_rgb_layer, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(sensor_secondary_row, text="Check Mixed Alignment", command=self.observatory_show_cross_sensor_alignment).pack(side="left")
        ttk.Button(sensor_secondary_row, text="Mixed Recipe", command=self.observatory_show_mixed_rgb_recipe).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_secondary_row, text="Save Recipe", command=self.observatory_save_mixed_rgb_recipe).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_secondary_row, text="Save Plan", command=self.observatory_save_sensor_rgb_plan).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_secondary_row, text="Copy Sensors", command=self.observatory_copy_sensor_summary).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_secondary_row, text="Export Sensors", command=self.observatory_export_sensor_summary_csv).pack(side="left", padx=(8, 0))
        ttk.Button(sensor_secondary_row, text="Show Selected Sensor", command=self.observatory_use_selected_sensor).pack(side="left", padx=(8, 0))
        self.sensor_status_var = tk.StringVar(value="Run a search to populate sensor coverage.")
        ttk.Label(sensor_filter_row, textvariable=self.sensor_status_var, wraplength=520).pack(side="left", padx=(12, 0), fill="x", expand=True)
        self.sensor_summary_list = tk.Listbox(
            sensor_panel,
            height=4,
            exportselection=False,
            bg="#ffffff",
            fg="#1f1f1f",
            selectbackground="#0067c0",
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        self.sensor_summary_list.pack(fill="x", pady=(6, 0))
        self.sensor_summary_list.bind("<Double-Button-1>", lambda _event: self.observatory_use_selected_sensor())
        self.observatory_update_sensor_dashboard()

        body = ttk.PanedWindow(observatory_content, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        report_tools = ttk.Frame(left)
        report_tools.pack(fill="x")
        ttk.Label(report_tools, text="Explorer Report", style="Section.TLabel").pack(side="left")
        ttk.Button(report_tools, text="Copy Report", command=self.observatory_copy_report).pack(side="right")
        ttk.Button(report_tools, text="Save Report", command=self.observatory_save_report).pack(side="right", padx=(0, 8))
        ttk.Button(report_tools, text="Copy Project Plan", command=self.observatory_copy_project_plan).pack(side="right", padx=(0, 8))
        ttk.Button(report_tools, text="Save Project Plan", command=self.observatory_save_project_plan).pack(side="right", padx=(0, 8))
        ttk.Button(report_tools, text="Load Project Plan", command=self.observatory_load_project_plan).pack(side="right", padx=(0, 8))
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

        mosaic_tools = ttk.Frame(right)
        mosaic_tools.pack(fill="x")
        mosaic_filter_row = ttk.Frame(mosaic_tools)
        mosaic_filter_row.pack(fill="x")
        mosaic_view_row = ttk.Frame(mosaic_tools)
        mosaic_view_row.pack(fill="x", pady=(4, 0))
        mosaic_rgb_row = ttk.Frame(mosaic_tools)
        mosaic_rgb_row.pack(fill="x", pady=(4, 0))
        mosaic_export_row = ttk.Frame(mosaic_tools)
        mosaic_export_row.pack(fill="x", pady=(4, 0))
        ttk.Label(mosaic_filter_row, text="Sky Mosaic / Coverage Map", style="Section.TLabel").pack(side="left")
        ttk.Label(mosaic_filter_row, text="Layer").pack(side="left", padx=(18, 6))
        self.mosaic_layer_var = tk.StringVar(value="All active sources")
        self.mosaic_layer_combo = ttk.Combobox(
            mosaic_filter_row,
            textvariable=self.mosaic_layer_var,
            values=["All active sources", "Hubble / HST", "JWST"],
            state="readonly",
            width=18,
        )
        self.mosaic_layer_combo.pack(side="left")
        self.mosaic_layer_combo.bind("<<ComboboxSelected>>", lambda _event: self.observatory_draw_current_mosaic())
        ttk.Label(mosaic_filter_row, text="Color").pack(side="left", padx=(12, 6))
        self.mosaic_color_mode_var = tk.StringVar(value="Wavelength")
        self.mosaic_color_mode_combo = ttk.Combobox(
            mosaic_filter_row,
            textvariable=self.mosaic_color_mode_var,
            values=["Wavelength", "Mission", "Instrument", "Exposure"],
            state="readonly",
            width=12,
        )
        self.mosaic_color_mode_combo.pack(side="left")
        self.mosaic_color_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.observatory_draw_current_mosaic())
        self.mosaic_best_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            mosaic_filter_row,
            text="Best candidates only",
            variable=self.mosaic_best_only_var,
            command=self.observatory_draw_current_mosaic,
        ).pack(side="left", padx=(14, 0))
        self.mosaic_overlap_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            mosaic_filter_row,
            text="Overlap only",
            variable=self.mosaic_overlap_only_var,
            command=self.observatory_draw_current_mosaic,
        ).pack(side="left", padx=(10, 0))
        self.mosaic_footprints_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            mosaic_filter_row,
            text="Footprints",
            variable=self.mosaic_footprints_var,
            command=self.observatory_draw_current_mosaic,
        ).pack(side="left", padx=(10, 0))
        ttk.Button(mosaic_filter_row, text="Coverage Summary", command=self.observatory_show_mosaic_coverage).pack(side="left", padx=(14, 0))
        ttk.Label(mosaic_view_row, text="Map Navigation", style="Section.TLabel").pack(side="left")
        ttk.Button(mosaic_view_row, text="Zoom +", command=lambda: self.observatory_mosaic_zoom(1.25)).pack(side="left", padx=(12, 0))
        ttk.Button(mosaic_view_row, text="Zoom -", command=lambda: self.observatory_mosaic_zoom(0.8)).pack(side="left", padx=(4, 0))
        ttk.Button(mosaic_view_row, text="Focus Selected", command=self.observatory_mosaic_focus_selected).pack(side="left", padx=(4, 0))
        ttk.Button(mosaic_view_row, text="Fit All", command=self.observatory_mosaic_reset_view).pack(side="left", padx=(4, 0))
        ttk.Button(mosaic_view_row, text="View Summary", command=self.observatory_show_mosaic_current_view).pack(side="left", padx=(4, 0))
        ttk.Label(mosaic_view_row, text="Scroll: zoom | Shift-drag: region | middle/right-drag: pan | double-click: focus").pack(side="left", padx=(12, 0))
        ttk.Button(mosaic_rgb_row, text="Mosaic RGB Plan", command=self.observatory_show_mosaic_rgb_plan, style="Accent.TButton").pack(side="left")
        ttk.Button(mosaic_rgb_row, text="Next RGB Pick", command=self.observatory_select_next_mosaic_rgb_pick, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="Get RGB Pick Products", command=self.observatory_get_mosaic_rgb_pick_products, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="Auto RGB Products", command=self.observatory_auto_collect_mosaic_rgb_products, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="RGB Progress", command=self.observatory_show_mosaic_rgb_progress).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="Copy RGB Progress", command=self.observatory_copy_mosaic_rgb_progress).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="Reset RGB Progress", command=self.observatory_reset_mosaic_rgb_progress).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="Copy RGB Plan", command=self.observatory_copy_mosaic_rgb_plan).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_rgb_row, text="Export RGB Plan", command=self.observatory_export_mosaic_rgb_plan_csv).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Overlap Candidates", command=self.observatory_show_overlap_candidates).pack(side="left")
        ttk.Button(mosaic_export_row, text="Select Best", command=self.observatory_select_best_overlap_candidate, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Copy Overlap", command=self.observatory_copy_overlap_candidates).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Export Overlap", command=self.observatory_export_overlap_candidates_csv).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Get Marker Products", command=self.observatory_get_marker_products, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Copy Marker Details", command=self.observatory_copy_marker_details).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Copy Mosaic Rows", command=self.observatory_copy_mosaic_rows).pack(side="left", padx=(8, 0))
        ttk.Button(mosaic_export_row, text="Export Mosaic CSV", command=self.observatory_export_mosaic_csv).pack(side="left", padx=(8, 0))
        self.mosaic_canvas = tk.Canvas(right, bg="#111827", highlightthickness=0, height=520)
        self.mosaic_canvas.pack(fill="both", expand=True, pady=(4, 0))
        self.mosaic_hover_var = tk.StringVar(value="Hover over a marker or footprint for details. Scroll to zoom; Shift-drag a region; left-click to select.")
        ttk.Label(right, textvariable=self.mosaic_hover_var, wraplength=720, style="Section.TLabel").pack(anchor="w", pady=(6, 0))
        self.mosaic_status_var = tk.StringVar(value="Run a MAST search, then click Analyze Current Search or Build Sky Mosaic View.")
        ttk.Label(right, textvariable=self.mosaic_status_var, wraplength=720).pack(anchor="w", pady=(6, 0))
        self.mosaic_canvas.bind("<Configure>", lambda _event: self.observatory_draw_current_mosaic())
        self.mosaic_canvas.bind("<Button-1>", self.observatory_mosaic_click)
        self.mosaic_canvas.bind("<Double-Button-1>", self.observatory_mosaic_double_click)
        self.mosaic_canvas.bind("<Shift-ButtonPress-1>", self.observatory_mosaic_region_start)
        self.mosaic_canvas.bind("<Shift-B1-Motion>", self.observatory_mosaic_region_move)
        self.mosaic_canvas.bind("<Shift-ButtonRelease-1>", self.observatory_mosaic_region_end)
        self.mosaic_canvas.bind("<Motion>", self.observatory_mosaic_hover)
        self.mosaic_canvas.bind("<MouseWheel>", self.observatory_mosaic_wheel)
        self.mosaic_canvas.bind("<Button-4>", self.observatory_mosaic_wheel)
        self.mosaic_canvas.bind("<Button-5>", self.observatory_mosaic_wheel)
        for button in (2, 3):
            self.mosaic_canvas.bind(f"<ButtonPress-{button}>", self.observatory_mosaic_pan_start)
            self.mosaic_canvas.bind(f"<B{button}-Motion>", self.observatory_mosaic_pan_move)
            self.mosaic_canvas.bind(f"<ButtonRelease-{button}>", self.observatory_mosaic_pan_end)

    def observatory_analyze_current(self):
        return super().observatory_analyze_current()

    def observatory_draw_current_mosaic(self):
        return super().observatory_draw_current_mosaic()

    def observatory_mosaic_click(self, event):
        return super().observatory_mosaic_click(event)

    def observatory_mosaic_reset_view(self):
        return super().observatory_mosaic_reset_view()

    def observatory_mosaic_focus_selected(self):
        return super().observatory_mosaic_focus_selected()

    def observatory_show_mosaic_current_view(self):
        return super().observatory_show_mosaic_current_view()

    def observatory_get_marker_products(self):
        return super().observatory_get_marker_products()

    def observatory_show_mosaic_coverage(self):
        return super().observatory_show_mosaic_coverage()

    def observatory_show_mosaic_rgb_plan(self):
        return super().observatory_show_mosaic_rgb_plan()

    def observatory_select_next_mosaic_rgb_pick(self):
        return super().observatory_select_next_mosaic_rgb_pick()

    def observatory_get_mosaic_rgb_pick_products(self):
        return super().observatory_get_mosaic_rgb_pick_products()

    def observatory_show_mosaic_rgb_progress(self):
        return super().observatory_show_mosaic_rgb_progress()

    def observatory_auto_collect_mosaic_rgb_products(self):
        return super().observatory_auto_collect_mosaic_rgb_products()

    def observatory_copy_mosaic_rgb_progress(self):
        return super().observatory_copy_mosaic_rgb_progress()

    def observatory_reset_mosaic_rgb_progress(self):
        return super().observatory_reset_mosaic_rgb_progress()

    def observatory_copy_mosaic_rgb_plan(self):
        return super().observatory_copy_mosaic_rgb_plan()

    def observatory_export_mosaic_rgb_plan_csv(self):
        return super().observatory_export_mosaic_rgb_plan_csv()

    def observatory_show_overlap_candidates(self):
        return super().observatory_show_overlap_candidates()

    def observatory_select_best_overlap_candidate(self):
        return super().observatory_select_best_overlap_candidate()

    def observatory_copy_overlap_candidates(self):
        return super().observatory_copy_overlap_candidates()

    def observatory_export_overlap_candidates_csv(self):
        return super().observatory_export_overlap_candidates_csv()

    def observatory_copy_marker_details(self):
        return super().observatory_copy_marker_details()

    def observatory_copy_report(self):
        return super().observatory_copy_report()

    def observatory_save_report(self):
        return super().observatory_save_report()

    def observatory_copy_project_plan(self):
        return super().observatory_copy_project_plan()

    def observatory_save_project_plan(self):
        return super().observatory_save_project_plan()

    def observatory_load_project_plan(self):
        return super().observatory_load_project_plan()

    def observatory_export_mosaic_csv(self):
        return super().observatory_export_mosaic_csv()

    def observatory_copy_mosaic_rows(self):
        return super().observatory_copy_mosaic_rows()

    def observatory_search_wider_async(self):
        return super().observatory_search_wider_async()

    def observatory_prepare_best_rgb_layer(self):
        return super().observatory_prepare_best_rgb_layer()


    def observatory_show_sensor_report(self):
        return super().observatory_show_sensor_report()

    def observatory_update_sensor_dashboard(self):
        return super().observatory_update_sensor_dashboard()

    def observatory_use_selected_sensor(self):
        return super().observatory_use_selected_sensor()


    def observatory_show_sensor_readiness(self):
        return super().observatory_show_sensor_readiness()

    def observatory_use_best_sensor(self):
        return super().observatory_use_best_sensor()

    def observatory_show_sensor_rgb_plan(self):
        return super().observatory_show_sensor_rgb_plan()

    def observatory_prepare_sensor_rgb_layer(self):
        return super().observatory_prepare_sensor_rgb_layer()

    def observatory_show_cross_sensor_rgb_plan(self):
        return super().observatory_show_cross_sensor_rgb_plan()

    def observatory_show_cross_sensor_alignment(self):
        return super().observatory_show_cross_sensor_alignment()

    def observatory_show_mixed_rgb_recipe(self):
        return super().observatory_show_mixed_rgb_recipe()

    def observatory_save_mixed_rgb_recipe(self):
        return super().observatory_save_mixed_rgb_recipe()

    def observatory_prepare_cross_sensor_rgb_layer(self):
        return super().observatory_prepare_cross_sensor_rgb_layer()

    def observatory_save_sensor_rgb_plan(self):
        return super().observatory_save_sensor_rgb_plan()

    def observatory_copy_sensor_summary(self):
        return super().observatory_copy_sensor_summary()

    def observatory_export_sensor_summary_csv(self):
        return super().observatory_export_sensor_summary_csv()


    def observatory_show_composition_strategy(self):
        return super().observatory_show_composition_strategy()

    def observatory_show_composition_readiness(self):
        return super().observatory_show_composition_readiness()

    def build_convert_tab(self):
        convert_content = self.build_scrollable_tab_content(self.convert_tab)
        top = ttk.Frame(convert_content)
        top.pack(fill="x")
        self.convert_path_var = tk.StringVar(value="")
        ttk.Button(top, text="Choose FITS", command=self.choose_convert_file).pack(side="left")
        ttk.Entry(top, textvariable=self.convert_path_var).pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.stretch_var = tk.StringVar(value="asinh")
        ttk.Combobox(top, textvariable=self.stretch_var, values=["asinh", "pow", "sqrt", "log", "linear"], state="readonly", width=8).pack(side="left")
        ttk.Button(top, text="Preview", command=self.preview_fits_async).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Save PNG/TIFF", command=self.save_preview_outputs).pack(side="left", padx=(8, 0))

        body = ttk.PanedWindow(convert_content, orient="horizontal")
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
        ttk.Label(convert_content, textvariable=self.convert_status).pack(anchor="w", pady=(6, 0))

    def build_compose_tab(self):
        compose_content = self.build_scrollable_tab_content(self.compose_tab)
        form = ttk.Frame(compose_content)
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

        controls = ttk.Frame(compose_content)
        controls.pack(fill="x", pady=(6, 8))
        self.compose_stretch_var = tk.StringVar(value="asinh")
        self.high_quality_var = tk.BooleanVar(value=SETTINGS.get("high_quality_processing", True))
        self.prefer_drizzled_var = tk.BooleanVar(value=SETTINGS.get("prefer_drizzled_products", True))
        self.presentation_cleanup_var = tk.BooleanVar(value=SETTINGS.get("presentation_cleanup", True))
        self.use_fits_liberator_var = tk.BooleanVar(value=SETTINGS.get("use_fits_liberator_engine", True))
        self.mosaic_coverage_mode_var = tk.StringVar(value="Full mosaic")
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

        coverage_controls = ttk.Frame(compose_content)
        coverage_controls.pack(fill="x", pady=(0, 8))
        ttk.Label(coverage_controls, text="Mosaic coverage").pack(side="left")
        ttk.Combobox(
            coverage_controls,
            textvariable=self.mosaic_coverage_mode_var,
            values=["Full mosaic", "Shared exposure overlap"],
            state="readonly",
            width=25,
        ).pack(side="left", padx=(8, 8))
        ttk.Button(coverage_controls, text="Stack Coverage Report", command=self.show_stack_coverage_report).pack(side="left")
        ttk.Label(coverage_controls, text="Shared mode can discard large low-overlap areas.").pack(side="left", padx=(10, 0))

        tuning = ttk.Frame(compose_content)
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
        ttk.Button(tuning, text="Auto Balance Color", command=self.auto_balance_color).grid(
            row=0, column=3, rowspan=7, sticky="ns", padx=(10, 0), pady=2
        )

        presentation = ttk.Frame(compose_content)
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

        advanced = ttk.LabelFrame(compose_content, text="Advanced stretch before preview")
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

        presets = ttk.Frame(compose_content)
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

        compare = ttk.LabelFrame(compose_content, text="Try Looks")
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

        thumbs = ttk.Frame(compose_content)
        thumbs.pack(fill="x", pady=(0, 8))
        self.channel_thumbnail_canvases = {}
        for label in ("Blue", "Green", "Red"):
            frame = ttk.Frame(thumbs)
            frame.pack(side="left", fill="x", expand=True, padx=(0 if label == "Blue" else 8, 0))
            ttk.Label(frame, text=f"{label} Preview", style="Section.TLabel").pack(anchor="w")
            canvas = tk.Canvas(frame, height=96, bg="#111827", highlightthickness=0)
            canvas.pack(fill="x")
            self.channel_thumbnail_canvases[label.lower()] = canvas

        self.rgb_canvas = tk.Canvas(compose_content, bg="#111827", highlightthickness=0)
        self.rgb_canvas.pack(fill="both", expand=True)
        self.compose_status = tk.StringVar(value="")
        self.compose_progress = ttk.Progressbar(compose_content, mode="indeterminate")
        self.compose_progress.pack(fill="x", pady=(6, 0))
        ttk.Label(compose_content, textvariable=self.compose_status).pack(anchor="w", pady=(6, 0))
        self.why_var = tk.StringVar(value="")
        ttk.Label(compose_content, textvariable=self.why_var, wraplength=1080).pack(anchor="w", pady=(0, 4))

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
        return super().search_async()

    def search_selected_sensor_async(self):
        return super().search_selected_sensor_async()

    def easy_high_quality_async(self):
        return super().easy_high_quality_async()

    def easy_rgb_async(self, high_quality=False):
        return super().easy_rgb_async(high_quality)

    def easy_all_sensors_async(self):
        return super().easy_all_sensors_async()

    def hla_search_async(self, fallback_message=None):
        return super().hla_search_async(fallback_message)

    def refresh_product_list(self):
        return super().refresh_product_list()

    def copy_selected_products(self, event=None):
        return super().copy_selected_products(event)

    def copy_all_products(self):
        return super().copy_all_products()

    def select_best_rgb_products(self):
        return super().select_best_rgb_products()

    def use_best_rgb_set(self):
        return super().use_best_rgb_set()

    def use_suggested_rgb_set(self):
        return super().use_suggested_rgb_set()

    def pick_best_available_rgb_channels(self):
        return super().pick_best_available_rgb_channels()

    def download_rgb_candidates_async(self):
        return super().download_rgb_candidates_async()

    def download_easy_all_sensors_rgb_async(self):
        return super().download_easy_all_sensors_rgb_async()

    def save_easy_all_sensors_summary(self):
        return super().save_easy_all_sensors_summary()

    def copy_easy_all_sensors_summary(self):
        return super().copy_easy_all_sensors_summary()

    def open_latest_easy_all_sensors_summary(self):
        return super().open_latest_easy_all_sensors_summary()

    def open_easy_all_sensors_summary_folder(self):
        return super().open_easy_all_sensors_summary_folder()

    def open_easy_all_sensors_run_index(self):
        return super().open_easy_all_sensors_run_index()

    def copy_latest_easy_all_sensors_run(self):
        return super().copy_latest_easy_all_sensors_run()

    def copy_latest_easy_all_sensors_run_id(self):
        return super().copy_latest_easy_all_sensors_run_id()

    def open_latest_easy_all_sensors_preview(self):
        return super().open_latest_easy_all_sensors_preview()

    def copy_latest_easy_all_sensors_preview_path(self):
        return super().copy_latest_easy_all_sensors_preview_path()

    def open_latest_easy_all_sensors_run_folder(self):
        return super().open_latest_easy_all_sensors_run_folder()

    def copy_rgb_candidates(self):
        return super().copy_rgb_candidates()

    def better_sources_async(self):
        return super().better_sources_async()

    def completeness_check_async(self):
        return super().completeness_check_async()

    def products_async(self):
        return super().products_async()

    def products_all_async(self):
        return super().products_all_async()

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

    def auto_balance_color(self):
        return super().auto_balance_color()

    def show_stack_coverage_report(self):
        return super().show_stack_coverage_report()

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

