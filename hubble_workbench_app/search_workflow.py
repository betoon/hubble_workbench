import threading
import traceback
from datetime import datetime
from tkinter import messagebox

import numpy as np

from hubble_workbench_app.catalogs import TELESCOPE_CHOICES
from hubble_workbench_app.fits_io import OBSERVATIONS
from hubble_workbench_app.paths import DOWNLOAD_DIR, SEARCH_LOG_DIR
from hubble_workbench_app.settings import SETTINGS, save_settings


class SearchWorkflowMixin:
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
            if getattr(self, "easy_all_sensors_pending_stage", None) == "search":
                self.easy_all_sensors_pending_stage = None
            if TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST":
                self.stop_browser_activity(f"MAST search failed: {error}")
            else:
                self.hla_search_async(fallback_message=f"MAST search failed: {error}. Trying HLA fallback...")
            return
        self.search_results = rows
        self.search_results_target = self.target_var.get().strip() if hasattr(self, "target_var") else ""
        self.product_results_target = ""
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
        if hasattr(self, "observatory_continue_easy_all_sensors_after_search"):
            try:
                self.after(250, self.observatory_continue_easy_all_sensors_after_search)
            except Exception:
                pass
