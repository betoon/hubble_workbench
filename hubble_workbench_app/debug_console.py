import logging
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from hubble_workbench_app.paths import DEBUG_LOG_PATH, LOG_DIR


class TkConsoleLogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__(level=logging.INFO)
        self.app = app
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            message = self.format(record)
            self.app.after(0, lambda: self.app.debug_console_write(message))
        except Exception:
            pass


class DebugConsoleMixin:
    def build_debug_console_tab(self):
        header = ttk.Frame(self.debug_tab)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Debug Console", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Clear", command=self.clear_debug_console).pack(side="right")
        ttk.Button(header, text="Save Console", command=self.save_debug_console).pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Open Debug File", command=self.open_debug_log_file).pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Refresh From Debug File", command=self.refresh_debug_console_from_file).pack(side="right", padx=(0, 8))

        self.debug_console_text = tk.Text(
            self.debug_tab,
            wrap="word",
            bg="#050505",
            fg="#ffd84d",
            insertbackground="#ffd84d",
            relief="flat",
            padx=12,
            pady=10,
            font=("Consolas", 10),
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(self.debug_tab, orient="vertical", command=self.debug_console_text.yview)
        self.debug_console_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.debug_console_text.pack(side="left", fill="both", expand=True)

        self.debug_console_write("Debug console ready. Live progress and app log messages will appear here.")
        self.debug_console_write(f"Full debug file: {DEBUG_LOG_PATH}")
        self.install_debug_console_logging()

    def install_debug_console_logging(self):
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, TkConsoleLogHandler):
                handler.app = self
                return
        root_logger.addHandler(TkConsoleLogHandler(self))

    def debug_console_write(self, message):
        widget = getattr(self, "debug_console_text", None)
        if widget is None:
            return
        if not message:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = str(message)
        if line[:8].count(":") != 2:
            line = f"{timestamp} {line}"
        try:
            widget.configure(state="normal")
            widget.insert("end", line.rstrip() + "\n")
            widget.see("end")
            widget.configure(state="disabled")
        except Exception:
            pass

    def clear_debug_console(self):
        widget = getattr(self, "debug_console_text", None)
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")
        self.debug_console_write("Debug console cleared.")

    def refresh_debug_console_from_file(self):
        if not DEBUG_LOG_PATH.exists():
            self.debug_console_write(f"Debug file does not exist yet: {DEBUG_LOG_PATH}")
            return
        try:
            lines = DEBUG_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-400:]
            widget = getattr(self, "debug_console_text", None)
            if widget is None:
                return
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("end", "Last lines from debug_hubble.txt\n")
            widget.insert("end", "=" * 80 + "\n")
            widget.insert("end", "\n".join(tail) + "\n")
            widget.see("end")
            widget.configure(state="disabled")
        except Exception as exc:
            self.debug_console_write(f"Could not refresh debug file: {exc}")

    def save_debug_console(self):
        widget = getattr(self, "debug_console_text", None)
        if widget is None:
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        default_name = "hubble_console_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        path = filedialog.asksaveasfilename(
            title="Save Debug Console",
            initialdir=str(LOG_DIR),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            text = widget.get("1.0", "end").strip() + "\n"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.debug_console_write(f"Saved visible console to {path}")
        except Exception as exc:
            messagebox.showerror("Save Debug Console", str(exc))

    def open_debug_log_file(self):
        if DEBUG_LOG_PATH.exists():
            self.open_file(DEBUG_LOG_PATH)
        else:
            self.debug_console_write(f"Debug file does not exist yet: {DEBUG_LOG_PATH}")
