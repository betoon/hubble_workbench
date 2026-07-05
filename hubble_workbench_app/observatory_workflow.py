import logging
import math
import threading
from tkinter import messagebox

from hubble_workbench_app.paths import ENHANCED_PRODUCT_TOKENS, SEARCH_LOG_DIR
from hubble_workbench_app.catalogs import HST_BLUE_FILTERS, HST_GREEN_FILTERS, HST_RED_FILTERS, TELESCOPE_CHOICES
from hubble_workbench_app.observatory_sources import active_sources, planned_sources, project_plan_lines, project_state


class ObservatoryWorkflowMixin:
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

    @staticmethod
    def observatory_top_counts(counts, limit=8):
        items = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[:limit]
        return ", ".join(f"{key}={value}" for key, value in items) or "none"

    def observatory_observation_label(self, row):
        obs_id = row.get("obs_id", "") or row.get("obsid", "") or "unknown observation"
        mission = row.get("obs_collection", "") or "Unknown"
        instrument = row.get("instrument_name", "") or "Unknown instrument"
        filters = row.get("filters", "") or row.get("Spectral_Elt", "") or "no filter listed"
        exposure = row.get("t_exptime", "") or "?"
        bucket = self.observation_filter_bucket(row)
        return f"{mission} | {obs_id} | {instrument} | {filters} | {exposure}s | {bucket}"

    def observatory_best_observations(self, rows, limit=8):
        scored = []
        for row in rows:
            score = 0
            if self.numeric_row_value(row, "s_ra", "ra", "RA") is not None:
                score += 10
            if self.numeric_row_value(row, "s_dec", "dec", "DEC") is not None:
                score += 10
            try:
                score += min(20, int(float(row.get("t_exptime", 0) or 0) / 100))
            except Exception:
                pass
            bucket = self.observation_filter_bucket(row)
            if bucket != "Unknown/other":
                score += 12
            if str(row.get("obs_collection", "")).upper() in ("HST", "JWST"):
                score += 5
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], self.observatory_observation_label(item[1])))
        return [row for _score, row in scored[:limit]]

    def observatory_product_highlights(self, rows, limit=8):
        highlighted = []
        for row in rows:
            score = self.product_quality_score(row)
            if self.product_rgb_channel(row):
                score += 20
            if row.get("_source") == "HLA":
                score += 15
            highlighted.append((score, row))
        highlighted.sort(key=lambda item: (-item[0], str(item[1].get("productFilename", ""))))
        return [row for _score, row in highlighted[:limit]]

    def observatory_recommendations(self, summary):
        missing_channels = [channel for channel, count in summary["channels"].items() if not count]
        recommendations = []
        if not summary["observations"]:
            recommendations.append("Run Search MAST first so the explorer has observations to analyze.")
        if summary["observations"] and summary["coordinate_rows"] < 2:
            recommendations.append("Use Search Wider Radius to collect more coordinate-bearing observations for the mosaic view.")
        if not summary["products"]:
            recommendations.append("Use Get Products or Get All Products to let the explorer evaluate FITS/product coverage.")
        if missing_channels:
            recommendations.append("Missing RGB coverage for: " + ", ".join(channel.title() for channel in missing_channels) + ".")
        if summary["products"] and not summary["enhanced_products"] and not summary["hla_products"]:
            recommendations.append("Run Find Better Sources to look for drizzled, mosaic, combined, HLA, or JWST i2d products.")
        if summary["rgb_sets"]:
            recommendations.append("A complete RGB set is available. Use Select Best RGB Products or Easy High Quality next.")
        elif all(summary["channels"][channel] for channel in ("blue", "green", "red")):
            recommendations.append("Blue, green, and red candidates exist, but they may not be aligned. Try Get All Products or Find Better Sources.")
        if not recommendations:
            recommendations.append("Current search looks usable. Review the highlighted products and compose a test RGB image.")
        return recommendations

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
        products_by_mission = {}
        channels_by_mission = {}
        for row in product_rows:
            name = str(row.get("productFilename", "")).lower()
            mission = str(row.get("obs_collection", "") or row.get("mission", "") or "Unknown").upper()
            if row.get("_source") == "HLA":
                mission = "HST"
            products_by_mission[mission] = products_by_mission.get(mission, 0) + 1
            channels_by_mission.setdefault(mission, {"blue": 0, "green": 0, "red": 0})
            if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
                enhanced += 1
            if row.get("_source") == "HLA":
                hla += 1
            channel = self.product_rgb_channel(row)
            if channel in channels:
                channels[channel] += 1
                channels_by_mission[mission][channel] += 1
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
            "products_by_mission": products_by_mission,
            "channels_by_mission": channels_by_mission,
            "rgb_sets": len(rgb_sets),
        }

    def observatory_summary_text(self):
        target = self.target_var.get().strip() or "(no target)"
        obs_rows = list(getattr(self, "search_results", []) or [])
        product_rows = list(getattr(self, "product_results", []) or [])
        summary = self.compute_observatory_summary(obs_rows, product_rows)
        lines = []
        lines.append(f"Target: {target}")
        lines.append(f"Current telescope setting: {self.telescope_var.get()}")
        lines.append(f"Current radius: {self.radius_var.get()}")
        lines.append("")
        lines.append("Observation Explorer:")
        lines.append(f"- Loaded observations: {summary['observations']}")
        lines.append(f"- Observations with sky coordinates: {summary['coordinate_rows']}")
        lines.append(f"- Total exposure time listed: {summary['exposure_total']:.1f} seconds")
        lines.append("- Missions: " + self.observatory_top_counts(summary["by_mission"]))
        lines.append("- Instruments: " + self.observatory_top_counts(summary["by_instrument"], limit=10))
        lines.append("- Wavelength buckets: " + self.observatory_top_counts(summary["by_filter"]))
        lines.append("")
        lines.append("Best observation candidates:")
        best_observations = self.observatory_best_observations(obs_rows)
        if best_observations:
            for index, row in enumerate(best_observations, start=1):
                lines.append(f"{index}. {self.observatory_observation_label(row)}")
        else:
            lines.append("- No observation rows are loaded yet.")
        lines.append("")
        lines.append("Product and RGB coverage:")
        lines.append(f"- Loaded FITS/products: {summary['products']}")
        lines.append(f"- Mosaic/drizzled/i2d/combined candidates: {summary['enhanced_products']}")
        lines.append(f"- HLA enhanced products: {summary['hla_products']}")
        lines.append(f"- RGB channel candidates: blue={summary['channels']['blue']}, green={summary['channels']['green']}, red={summary['channels']['red']}")
        lines.append(f"- Complete RGB sets: {summary['rgb_sets']}")
        highlighted = self.observatory_product_highlights(product_rows)
        if highlighted:
            lines.append("")
            lines.append("Highlighted products:")
            for index, row in enumerate(highlighted, start=1):
                channel = self.product_rgb_channel(row) or "no RGB channel"
                lines.append(f"{index}. {channel}: {self.product_label(row)}")
        lines.append("")
        lines.append("Sky Mosaic Viewer:")
        if summary["coordinate_rows"] >= 2:
            lines.append("- Ready. Each plotted marker is an observation center from MAST coordinates.")
        elif summary["coordinate_rows"] == 1:
            lines.append("- Limited. One coordinate-bearing observation is loaded; wider search can make the map useful.")
        else:
            lines.append("- Waiting for coordinate-bearing observations.")
        lines.append("")
        lines.append("Completeness Analyzer:")
        for recommendation in self.observatory_recommendations(summary):
            lines.append(f"- {recommendation}")
        lines.append("")
        lines.append("Multi-Telescope Project Plan:")
        for source_line in project_plan_lines(summary):
            lines.append(source_line)
        lines.append("")
        lines.append(
            f"Phase 3 foundation: {len(active_sources())} active source(s), "
            f"{len(planned_sources())} planned source layer(s). Planned sources are visible for project tracking and are not searched yet."
        )
        return "\n".join(lines)

    def observatory_analyze_current(self):
        try:
            report = self.observatory_summary_text()
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", report)
            self.observatory_draw_current_mosaic()
            summary = self.compute_observatory_summary()
            self.save_diagnostic_json(SEARCH_LOG_DIR, f"{self.current_target_for_log()}_observatory_explorer", {
                "target": self.current_target_for_log(),
                "summary": summary,
                "project_state": project_state(summary),
                "report": report,
            })
        except Exception as exc:
            logging.exception("Observatory Explorer analysis failed")
            messagebox.showerror("Observatory Explorer", self.format_error_message(exc))

    def observatory_marker_style(self, row):
        mission = str(row.get("obs_collection", "")).upper()
        bucket = self.observation_filter_bucket(row)
        if "Blue" in bucket:
            fill = "skyblue"
        elif "Green" in bucket:
            fill = "lightgreen"
        elif "Red" in bucket:
            fill = "salmon"
        elif mission == "JWST":
            fill = "cyan"
        else:
            fill = "white"
        outline = "#facc15" if mission == "JWST" else "#111827"
        return fill, outline, bucket

    @staticmethod
    def observatory_range_padding(minimum, maximum, fraction=0.08):
        span = maximum - minimum
        if abs(span) < 1e-6:
            span = 0.002
        padding = max(span * fraction, 0.0005)
        return minimum - padding, maximum + padding

    def observatory_draw_current_mosaic(self):
        canvas = getattr(self, "mosaic_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(400, int(canvas.winfo_width() or 700))
        height = max(300, int(canvas.winfo_height() or 500))
        rows = list(getattr(self, "search_results", []) or [])
        points = []
        mission_counts = {}
        bucket_counts = {}
        for row in rows:
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            if ra is None or dec is None:
                continue
            mission = str(row.get("obs_collection", "Unknown") or "Unknown")
            mission_counts[mission] = mission_counts.get(mission, 0) + 1
            bucket = self.observation_filter_bucket(row)
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            points.append((ra, dec, row))

        canvas.create_text(width // 2, 22, text="Sky Mosaic / Coverage Map", fill="#ffffff", font=("Segoe UI", 14, "bold"))
        if not points:
            canvas.create_text(
                width // 2,
                height // 2,
                text="No observation coordinates loaded yet.\nRun Search MAST, Search Wider Radius, or Find Better Sources.",
                fill="#ffffff",
                font=("Segoe UI", 11),
                justify="center",
            )
            self.mosaic_status_var.set("No coordinate-bearing observations available yet.")
            return

        ras = [p[0] for p in points]
        decs = [p[1] for p in points]
        ra_min, ra_max = self.observatory_range_padding(min(ras), max(ras))
        dec_min, dec_max = self.observatory_range_padding(min(decs), max(decs))
        ra_mid = (ra_min + ra_max) / 2
        dec_mid = (dec_min + dec_max) / 2
        margin_left = 72
        margin_right = 38
        margin_top = 58
        margin_bottom = 58
        plot_x0 = margin_left
        plot_y0 = margin_top
        plot_x1 = width - margin_right
        plot_y1 = height - margin_bottom
        plot_w = max(1, plot_x1 - plot_x0)
        plot_h = max(1, plot_y1 - plot_y0)

        def map_point(ra, dec):
            x = plot_x0 + (ra - ra_min) / (ra_max - ra_min) * plot_w
            y = plot_y1 - (dec - dec_min) / (dec_max - dec_min) * plot_h
            return x, y

        canvas.create_rectangle(plot_x0, plot_y0, plot_x1, plot_y1, outline="#6b7280")
        for i in range(6):
            x = plot_x0 + plot_w * i / 5
            y = plot_y0 + plot_h * i / 5
            ra_tick = ra_min + (ra_max - ra_min) * i / 5
            dec_tick = dec_max - (dec_max - dec_min) * i / 5
            canvas.create_line(x, plot_y0, x, plot_y1, fill="#1f2937")
            canvas.create_line(plot_x0, y, plot_x1, y, fill="#1f2937")
            canvas.create_text(x, plot_y1 + 16, text=f"{ra_tick:.4f}", fill="#d1d5db", font=("Segoe UI", 8))
            canvas.create_text(plot_x0 - 12, y, anchor="e", text=f"{dec_tick:.4f}", fill="#d1d5db", font=("Segoe UI", 8))

        mid_x, mid_y = map_point(ra_mid, dec_mid)
        canvas.create_line(mid_x, plot_y0, mid_x, plot_y1, fill="#374151", dash=(3, 4))
        canvas.create_line(plot_x0, mid_y, plot_x1, mid_y, fill="#374151", dash=(3, 4))
        canvas.create_text(plot_x0, 38, anchor="w", text="Marker size hints exposure time; color hints likely wavelength bucket.", fill="#d1d5db")

        for ra, dec, row in points[:1000]:
            x, y = map_point(ra, dec)
            fill, outline, _bucket = self.observatory_marker_style(row)
            size = 4
            try:
                exp = float(row.get("t_exptime", 0) or 0)
                size = min(12, max(3, int(3 + math.log10(max(exp, 1)))))
            except Exception:
                pass
            canvas.create_oval(x - size, y - size, x + size, y + size, fill=fill, outline=outline, width=1)

        legend_x = plot_x1 - 225
        legend_y = plot_y0 + 12
        canvas.create_rectangle(legend_x - 10, legend_y - 8, plot_x1 - 10, legend_y + 102, fill="#111827", outline="#374151")
        legend_items = [
            ("skyblue", "Blue/short"),
            ("lightgreen", "Green/mid"),
            ("salmon", "Red/IR"),
            ("cyan", "JWST/other"),
            ("white", "HST/other"),
        ]
        for index, (color, label) in enumerate(legend_items):
            y = legend_y + index * 20
            canvas.create_oval(legend_x, y, legend_x + 10, y + 10, fill=color, outline="#111827")
            canvas.create_text(legend_x + 18, y + 5, anchor="w", text=label, fill="#d1d5db", font=("Segoe UI", 8))

        canvas.create_text(plot_x0, height - 30, anchor="w", text=f"RA {ra_min:.5f} to {ra_max:.5f} deg", fill="#d1d5db")
        canvas.create_text(plot_x1, height - 30, anchor="e", text=f"Dec {dec_min:.5f} to {dec_max:.5f} deg", fill="#d1d5db")
        mission_text = self.observatory_top_counts(mission_counts, limit=5)
        bucket_text = self.observatory_top_counts(bucket_counts, limit=4)
        self.mosaic_status_var.set(
            f"Plotted {len(points)} observation centers. Missions: {mission_text}. Wavelength buckets: {bucket_text}. "
            "True footprint polygons remain a later Phase 2 upgrade."
        )

    def observatory_prepare_best_rgb_layer(self):
        product_rows = list(getattr(self, "product_results", []) or [])
        if not product_rows:
            self.observatory_analyze_current()
            message = "Get Products or Find Better Sources first, then prepare the best RGB layer."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            try:
                self.observatory_report_text.insert("end", "\n\nPrepare Best RGB Layer:\n- " + message)
                self.observatory_report_text.see("end")
            except Exception:
                pass
            return

        self.refresh_product_list()
        self.select_best_rgb_products()
        selected_count = 0
        try:
            selected_count = len(self.product_list.curselection())
        except Exception:
            selected_count = 0

        if selected_count:
            message = f"Prepared {selected_count} RGB product(s). Review the selected products in the MAST Browser RGB Picker, then download or compose."
        else:
            message = "No complete RGB layer could be prepared yet. Try Get All Products, Find Better Sources, or loosen product filters."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        try:
            self.browser_status.set(message)
        except Exception:
            pass
        try:
            self.notebook.select(self.browser_tab)
        except Exception:
            pass
        self.observatory_analyze_current()

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
