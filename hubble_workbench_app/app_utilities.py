import os

from PIL import Image, ImageTk


def responsive_window_layout(screen_width, screen_height, preferred_width=1160, preferred_height=760):
    """Return a conservative window and minimum size that fits the current display."""
    screen_width = max(640, int(screen_width))
    screen_height = max(480, int(screen_height))
    available_width = max(640, screen_width - 40)
    available_height = max(480, screen_height - 100)
    width = min(int(preferred_width), available_width)
    height = min(int(preferred_height), available_height)
    minimum_width = min(940, max(640, available_width - 80))
    minimum_height = min(620, max(480, available_height - 80))
    return {
        "width": width,
        "height": height,
        "minimum_width": min(minimum_width, width),
        "minimum_height": min(minimum_height, height),
        "x": max(0, (screen_width - width) // 2),
        "y": max(0, (screen_height - height) // 2),
    }


def responsive_toolbar_positions(available_width, item_widths, gap=6):
    """Assign toolbar items to rows without exceeding the available viewport width."""
    available_width = max(1, int(available_width))
    gap = max(0, int(gap))
    positions = []
    row = 0
    column = 0
    used = 0
    for width in item_widths:
        width = max(1, min(int(width), available_width))
        required = width if column == 0 else gap + width
        if column and used + required > available_width:
            row += 1
            column = 0
            used = 0
            required = width
        positions.append((row, column))
        used += required
        column += 1
    return positions


def responsive_tab_titles(available_width):
    if int(available_width) < 1050:
        return ("Setup", "MAST", "Explorer", "FITS", "Composer", "H-II", "Debug")
    return (
        "Setup",
        "MAST Browser",
        "Observatory Explorer",
        "FITS Preview / Convert",
        "Color Composer",
        "Hydrogen Enhance",
        "Debug Console",
    )


def responsive_content_height(viewport_height, reserved_height=260, minimum=280, maximum=520):
    available = int(viewport_height) - int(reserved_height)
    return max(int(minimum), min(int(maximum), available))


def responsive_pane_orientation(available_width, breakpoint=980):
    return "vertical" if int(available_width) < int(breakpoint) else "horizontal"


def mousewheel_scroll_units(delta):
    delta = int(delta or 0)
    if not delta:
        return 0
    magnitude = max(1, round(abs(delta) / 120.0))
    return -magnitude if delta > 0 else magnitude
from tkinter import messagebox

from hubble_workbench_app.settings import SETTINGS, save_settings


class AppUtilitiesMixin:
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
            os.startfile(str(folder))
        except Exception:
            messagebox.showinfo("Folder", str(folder))

    def open_file(self, path):
        try:
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("File", str(path))

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
