import threading
from tkinter import messagebox

from hubble_workbench_app.catalogs import TELESCOPE_CHOICES
from hubble_workbench_app.fits_io import OBSERVATIONS
from hubble_workbench_app.paths import ENHANCED_PRODUCT_TOKENS, SEARCH_LOG_DIR
from hubble_workbench_app.settings import SETTINGS, save_settings


class BetterSourcesMixin:
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

    def completeness_status_line(self, ok, label, detail):
        status = "OK" if ok else "Needs attention"
        return f"- {status}: {label} - {detail}"

    @staticmethod
    def completeness_best_names(rows, limit=3):
        names = [str(row.get("productFilename", "") or row.get("URL", "") or "product") for row in rows[:limit]]
        return ", ".join(names) if names else "none"

    def build_completeness_report(self, rows, target):
        rows = list(rows or [])
        channels = {"blue": [], "green": [], "red": []}
        enhanced = []
        hla = []
        direct_fits = []
        spectra = []
        by_group = {}
        for row in rows:
            name = str(row.get("productFilename", "")).lower()
            if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
                enhanced.append(row)
            if row.get("_source") == "HLA":
                hla.append(row)
            if self.product_is_direct_fits(row):
                direct_fits.append(row)
            if self.product_is_spectrum(row):
                spectra.append(row)
            channel = self.product_rgb_channel(row)
            if channel:
                channels[channel].append(row)
                group = by_group.setdefault(self.rgb_group_key(row), {"blue": 0, "green": 0, "red": 0})
                group[channel] += 1

        rgb_sets = self.suggest_rgb_sets_for_rows(rows, recipe=self.target_recipe(target)) if rows else []
        same_group = bool(rgb_sets and all(id(rgb_sets[0][channel]) in self.rgb_ready_product_ids for channel in ("blue", "green", "red")))
        complete_groups = [group for group in by_group.values() if all(group[channel] for channel in ("blue", "green", "red"))]
        missing_channels = [channel for channel in ("blue", "green", "red") if not channels[channel]]
        observations = list(getattr(self, "search_results", []) or [])
        coordinate_rows = sum(
            1 for row in observations
            if self.numeric_row_value(row, "s_ra", "ra", "RA") is not None
            and self.numeric_row_value(row, "s_dec", "dec", "DEC") is not None
        )
        wider_loaded = len(observations) > 1
        has_cleanup_check = hasattr(self, "presentation_cleanup_fills")

        lines = []
        lines.append(f"Target: {target or '(current product list)'}")
        lines.append(f"Products currently loaded: {len(rows)}")
        lines.append(f"Observations currently loaded: {len(observations)}")
        lines.append("")
        lines.append("Completeness checklist:")
        lines.append(self.completeness_status_line(bool(rows), "Product list", f"{len(rows)} product(s) loaded"))
        lines.append(self.completeness_status_line(bool(direct_fits), "Direct FITS products", f"{len(direct_fits)} direct FITS product(s), {len(spectra)} spectrum-like product(s)"))
        for channel in ("blue", "green", "red"):
            lines.append(self.completeness_status_line(bool(channels[channel]), f"{channel.title()} channel", f"{len(channels[channel])} candidate(s)"))
        lines.append(self.completeness_status_line(bool(rgb_sets), "Complete RGB set", f"{len(rgb_sets)} candidate set(s)"))
        lines.append(self.completeness_status_line(same_group or bool(complete_groups), "Alignment confidence", "same group confirmed" if same_group else f"{len(complete_groups)} possible complete group(s)"))
        lines.append(self.completeness_status_line(bool(enhanced or hla), "Enhanced products", f"{len(enhanced)} mosaic/drizzled/i2d/combined, {len(hla)} HLA"))
        lines.append(self.completeness_status_line(wider_loaded, "Wider observation context", f"{len(observations)} observation row(s), {coordinate_rows} with coordinates"))
        lines.append(self.completeness_status_line(has_cleanup_check, "Image-level cleanup check", f"presentation cleanup fills: {getattr(self, 'presentation_cleanup_fills', 'not run yet')}"))
        lines.append("")
        lines.append("Best available product hints:")
        if rgb_sets:
            best = rgb_sets[0]
            for channel in ("blue", "green", "red"):
                lines.append(f"- {channel.title()}: {self.product_label(best[channel])}")
        else:
            for channel in ("blue", "green", "red"):
                lines.append(f"- {channel.title()}: {self.completeness_best_names(channels[channel])}")
        lines.append("")
        lines.append("Missing or uncertain:")
        if missing_channels:
            lines.append("- Missing RGB channels: " + ", ".join(channel.title() for channel in missing_channels))
        if not same_group:
            lines.append("- Same-observation/alignment group is not fully confirmed.")
        if not enhanced and not hla:
            lines.append("- No enhanced mosaic/drizzled/i2d/HLA products are currently loaded.")
        if not wider_loaded:
            lines.append("- Wider search context has not been loaded yet.")
        if not missing_channels and same_group and (enhanced or hla):
            lines.append("- No major gaps found for a first RGB composition attempt.")
        lines.append("")
        lines.append("Recommended next action:")
        if not rows:
            lines.append("Run Find Better Sources, or run Search MAST followed by Get All Products.")
        elif missing_channels:
            lines.append("Run Get All Products or Find Better Sources to look for the missing color channels.")
        elif not same_group:
            lines.append("Use Find Better Sources to look for an aligned RGB set, or compose a test image and inspect registration.")
        elif not enhanced and not hla:
            lines.append("Run Find Better Sources to look for higher-quality mosaic/drizzled/i2d/HLA products before final export.")
        else:
            lines.append("Use Select Best RGB Products or Easy High Quality, then review the Color Composer output.")
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
