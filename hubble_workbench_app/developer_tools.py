import json
import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk

from hubble_workbench_app.paths import DEBUG_LOG_PATH, LOG_DIR
from hubble_workbench_app.settings import SETTINGS, save_settings

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
        logging.info("Developer diagnostic saved: %s", path)
        return path
    except Exception:
        logging.exception("Could not write developer JSON diagnostic")
        return None

class DeveloperToolsMixin:
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
            logging.info("Developer Tools menu installed")
        except Exception:
            logging.exception("Could not create Developer Tools menu")

    def save_developer_settings(self):
        SETTINGS["developer_mode"] = bool(self.developer_mode_var.get())
        SETTINGS["verbose_mast_logging"] = bool(self.verbose_mast_log_var.get())
        SETTINGS["save_search_history"] = bool(self.save_search_history_var.get())
        SETTINGS["save_product_lists"] = bool(self.save_product_lists_var.get())
        SETTINGS["save_download_logs"] = bool(self.save_download_logs_var.get())
        SETTINGS["save_timing_stats"] = bool(self.save_timing_stats_var.get())
        save_settings(SETTINGS)
        logging.info("Developer settings saved: %s", {key: SETTINGS.get(key) for key in ("developer_mode", "verbose_mast_logging", "save_search_history", "save_product_lists", "save_download_logs", "save_timing_stats")})

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
