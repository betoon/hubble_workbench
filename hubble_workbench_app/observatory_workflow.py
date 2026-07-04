import logging
import math
import threading
from tkinter import messagebox

from hubble_workbench_app.paths import ENHANCED_PRODUCT_TOKENS, SEARCH_LOG_DIR
from hubble_workbench_app.catalogs import HST_BLUE_FILTERS, HST_GREEN_FILTERS, HST_RED_FILTERS, TELESCOPE_CHOICES


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
            logging.exception("Observatory Explorer analysis failed")
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
