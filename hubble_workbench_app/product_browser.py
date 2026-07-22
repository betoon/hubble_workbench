import threading
from tkinter import messagebox

from hubble_workbench_app.catalogs import RGB_FILTER_TOKENS
from hubble_workbench_app.fits_io import OBSERVATIONS
from hubble_workbench_app.paths import PRODUCT_LOG_DIR


class ProductBrowserMixin:
    def product_scan_sensor_name(self, row):
        """Return a stable sensor label for balancing an observation scan."""
        classifier = getattr(self, "observatory_sensor_family", None)
        if callable(classifier):
            try:
                return classifier(row)
            except Exception:
                pass
        instrument = str(row.get("instrument_name", "") or row.get("Detector", "") or "").strip()
        mission = str(row.get("obs_collection", "") or row.get("mission", "") or "Unknown").strip()
        return instrument or f"Other {mission}"

    def sensor_balanced_observation_rows(self, rows, limit=60):
        """Round-robin observations by sensor so one archive block cannot fill the scan."""
        rows = list(rows or [])
        if limit <= 0 or len(rows) <= limit:
            return rows[:max(0, limit)]
        buckets = {}
        for row in rows:
            buckets.setdefault(self.product_scan_sensor_name(row), []).append(row)
        selected = []
        offset = 0
        while len(selected) < limit:
            added = False
            for sensor_rows in buckets.values():
                if offset < len(sensor_rows):
                    selected.append(sensor_rows[offset])
                    added = True
                    if len(selected) >= limit:
                        break
            if not added:
                break
            offset += 1
        return selected

    def product_scan_sensor_counts(self, rows):
        counts = {}
        for row in rows:
            name = self.product_scan_sensor_name(row)
            counts[name] = counts.get(name, 0) + 1
        return counts

    def product_matches_filters(self, row):
        text = self.product_filter_text(row)
        if hasattr(self, "observatory_row_matches_sensor_filter") and not self.observatory_row_matches_sensor_filter(row):
            return False
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
        for channel in self.rgb_candidate_rows:
            self.rgb_candidate_rows[channel].sort(key=lambda row: (-self.product_quality_score(row), self.product_sort_key(row)))
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
        for channel in candidate_rows:
            candidate_rows[channel].sort(key=lambda row: (-self.product_quality_score(row), self.product_sort_key(row)))
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
        stack_rows = self.rgb_stack_download_rows(self.product_results, rgb_set, per_channel=3)
        rows = self.unique_product_rows([
            row for channel in ("blue", "green", "red") for row in stack_rows[channel]
        ])
        self.download_product_rows_async(rows, "RGB_set", rgb_set=rgb_set, stack_rows=stack_rows)

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
        rows_to_scan = self.sensor_balanced_observation_rows(self.search_results, limit=60)
        self.last_product_scan_sensor_counts = self.product_scan_sensor_counts(rows_to_scan)
        sensor_detail = ", ".join(
            f"{name}: {count}" for name, count in self.last_product_scan_sensor_counts.items()
        )
        self.browser_timeout_seconds = 1800
        operation_id = self.start_browser_activity(
            f"Loading products from {len(rows_to_scan)} sensor-balanced observations ({sensor_detail})..."
        )
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
        for key in ("obs_collection", "instrument_name", "target_name", "filters", "obs_id", "s_fov", "s_region", "t_exptime", "t_min", "t_max", "proposal_id"):
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
            if hasattr(self, "observatory_continue_marker_preview_after_products"):
                self.observatory_continue_marker_preview_after_products([], error)
            if getattr(self, "easy_all_sensors_pending_stage", None) == "products":
                self.easy_all_sensors_pending_stage = None
            self.stop_browser_activity(f"Product lookup failed: {error}")
            return
        self.product_results = rows
        self.product_results_target = self.target_var.get().strip() if hasattr(self, "target_var") else ""
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
                "scanned_observations_by_sensor": getattr(self, "last_product_scan_sensor_counts", {}),
                "products": rows[:5000],
            })
        self.stop_browser_activity(
            f"Found {len(rows)} FITS products{' across observations' if all_observations else ''}. Showing {len(self.visible_product_results)} with the current filters."
        )
        if not all_observations and hasattr(self, "observatory_continue_marker_preview_after_products"):
            self.observatory_continue_marker_preview_after_products(rows)
        if hasattr(self, "observatory_continue_easy_all_sensors_after_products"):
            try:
                self.after(250, lambda: self.observatory_continue_easy_all_sensors_after_products(all_observations))
            except Exception:
                pass
