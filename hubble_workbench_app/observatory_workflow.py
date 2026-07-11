import csv
import json
import logging
import math
import threading
from tkinter import messagebox

from hubble_workbench_app.paths import ENHANCED_PRODUCT_TOKENS, SEARCH_LOG_DIR
from hubble_workbench_app.catalogs import HST_BLUE_FILTERS, HST_GREEN_FILTERS, HST_RED_FILTERS, TELESCOPE_CHOICES
from hubble_workbench_app.observatory_sources import active_sources, composition_readiness_lines, composition_readiness_state, composition_strategy_lines, planned_sources, project_checklist_lines, project_plan_lines, project_state


SENSOR_FAMILIES = [
    {
        "name": "WFC3 UVIS",
        "tokens": ("WFC3/UVIS", "WFC3 UVIS", "UVIS"),
        "mission": "HST",
        "role": "Hubble ultraviolet and visible imaging for crisp blue/green structure.",
    },
    {
        "name": "WFC3 IR",
        "tokens": ("WFC3/IR", "WFC3 IR"),
        "mission": "HST",
        "role": "Hubble near-infrared imaging for dust-penetrating red layers.",
    },
    {
        "name": "ACS WFC",
        "tokens": ("ACS/WFC", "ACS WFC", "ACS"),
        "mission": "HST",
        "role": "Hubble wide-field visible imaging and many classic color releases.",
    },
    {
        "name": "WFPC2",
        "tokens": ("WFPC2",),
        "mission": "HST",
        "role": "Legacy Hubble imaging useful for older targets and historical coverage.",
    },
    {
        "name": "NIRCam",
        "tokens": ("NIRCAM",),
        "mission": "JWST",
        "role": "JWST near-infrared imaging for high-detail dust and star-forming regions.",
    },
    {
        "name": "MIRI",
        "tokens": ("MIRI",),
        "mission": "JWST",
        "role": "JWST mid-infrared imaging for warm dust and embedded structure.",
    },
]


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

    def observatory_sensor_family(self, row):
        text = " ".join(str(row.get(key, "")) for key in (
            "instrument_name", "Detector", "obs_id", "productFilename", "filters", "Spectral_Elt"
        ))
        upper = text.upper()
        for sensor in SENSOR_FAMILIES:
            if any(token in upper for token in sensor["tokens"]):
                return sensor["name"]
        mission = str(row.get("obs_collection", "") or row.get("mission", "")).upper()
        if row.get("_source") == "HLA":
            mission = "HST"
        if mission == "HST":
            return "Other Hubble"
        if mission == "JWST":
            return "Other JWST"
        return "Unknown sensor"

    @staticmethod
    def observatory_sensor_catalog():
        return SENSOR_FAMILIES + [
            {"name": "Other Hubble", "tokens": (), "mission": "HST", "role": "Hubble rows where MAST did not expose a recognized imaging sensor name."},
            {"name": "Other JWST", "tokens": (), "mission": "JWST", "role": "JWST rows where MAST did not expose NIRCam or MIRI directly."},
            {"name": "Unknown sensor", "tokens": (), "mission": "Unknown", "role": "Rows with incomplete instrument metadata."},
        ]

    def observatory_sensor_filter_name(self):
        try:
            return self.sensor_filter_var.get()
        except Exception:
            return "All sensors"

    def observatory_row_matches_sensor_filter(self, row):
        sensor_filter = self.observatory_sensor_filter_name()
        return sensor_filter in ("", "All sensors") or self.observatory_sensor_family(row) == sensor_filter

    def observatory_sensor_summary(self, obs_rows=None, product_rows=None):
        obs_rows = list(obs_rows if obs_rows is not None else getattr(self, "search_results", []) or [])
        product_rows = list(product_rows if product_rows is not None else getattr(self, "product_results", []) or [])
        summary = {}
        for sensor in self.observatory_sensor_catalog():
            summary[sensor["name"]] = {
                "name": sensor["name"], "mission": sensor["mission"], "role": sensor["role"],
                "observations": 0, "products": 0, "coordinates": 0, "exposure": 0.0,
                "channels": {"blue": 0, "green": 0, "red": 0},
            }
        for row in obs_rows:
            sensor = self.observatory_sensor_family(row)
            item = summary.setdefault(sensor, {
                "name": sensor, "mission": str(row.get("obs_collection", "") or "Unknown"),
                "role": "Instrument family discovered from loaded observation metadata.",
                "observations": 0, "products": 0, "coordinates": 0, "exposure": 0.0,
                "channels": {"blue": 0, "green": 0, "red": 0},
            })
            item["observations"] += 1
            if self.numeric_row_value(row, "s_ra", "ra", "RA") is not None and self.numeric_row_value(row, "s_dec", "dec", "DEC") is not None:
                item["coordinates"] += 1
            try:
                item["exposure"] += float(row.get("t_exptime", 0) or 0)
            except Exception:
                pass
        for row in product_rows:
            sensor = self.observatory_sensor_family(row)
            item = summary.setdefault(sensor, {
                "name": sensor, "mission": str(row.get("obs_collection", "") or row.get("mission", "") or "Unknown"),
                "role": "Instrument family discovered from loaded product metadata.",
                "observations": 0, "products": 0, "coordinates": 0, "exposure": 0.0,
                "channels": {"blue": 0, "green": 0, "red": 0},
            })
            item["products"] += 1
            channel = self.product_rgb_channel(row)
            if channel in item["channels"]:
                item["channels"][channel] += 1
        return summary

    def observatory_sensor_rows(self):
        rows = []
        always_show = {"WFC3 UVIS", "WFC3 IR", "ACS WFC", "WFPC2", "NIRCam", "MIRI"}
        for item in self.observatory_sensor_summary().values():
            if item["observations"] or item["products"] or item["name"] in always_show:
                rows.append(item)
        rows.sort(key=lambda item: (-(item["observations"] + item["products"]), item["mission"], item["name"]))
        return rows

    def observatory_sensor_line(self, item):
        channels = item["channels"]
        return (
            f"{item['name']} ({item['mission']}): obs={item['observations']}, "
            f"products={item['products']}, coords={item['coordinates']}, "
            f"RGB B/G/R={channels['blue']}/{channels['green']}/{channels['red']}"
        )

    def observatory_update_sensor_dashboard(self):
        rows = self.observatory_sensor_rows()
        widget = getattr(self, "sensor_summary_list", None)
        if widget is not None:
            widget.delete(0, "end")
            for item in rows:
                widget.insert("end", self.observatory_sensor_line(item))
        try:
            loaded = [item for item in rows if item["observations"] or item["products"]]
            if loaded:
                strongest = loaded[0]
                self.sensor_status_var.set(
                    f"Strongest sensor now: {strongest['name']} with {strongest['observations']} observations and {strongest['products']} products."
                )
            else:
                self.sensor_status_var.set("Run a search to populate WFC3, ACS, WFPC2, NIRCam, MIRI, and other sensor coverage.")
        except Exception:
            pass
        return rows

    def observatory_sensor_report_text(self):
        target = self.target_var.get().strip() or "(no target)"
        lines = [f"Sensor and Instrument Coverage for {target}", ""]
        for item in self.observatory_sensor_rows():
            channels = item["channels"]
            lines.append(self.observatory_sensor_line(item))
            lines.append(f"- Role: {item['role']}")
            if item["observations"]:
                lines.append(f"- Exposure listed: {item['exposure']:.1f} seconds")
            if item["products"] and not all(channels[channel] for channel in ("blue", "green", "red")):
                missing = ", ".join(channel for channel in ("blue", "green", "red") if not channels[channel])
                lines.append(f"- Missing RGB product coverage: {missing}")
            elif item["products"]:
                lines.append("- Complete RGB product coverage is available for this sensor family.")
            lines.append("")
        lines.append("Use the Sensor filter above the mosaic to inspect one instrument family at a time.")
        return "\n".join(lines).strip()

    def observatory_show_sensor_report(self):
        text = self.observatory_sensor_report_text()
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set("Generated sensor and instrument coverage report.")
        self.observatory_update_sensor_dashboard()
        self.observatory_draw_current_mosaic()
        return text

    def observatory_use_selected_sensor(self):
        widget = getattr(self, "sensor_summary_list", None)
        if widget is None:
            return None
        try:
            selection = widget.curselection()
        except Exception:
            selection = ()
        rows = self.observatory_sensor_rows()
        if not selection or selection[0] >= len(rows):
            message = "Select a sensor row first."
            if hasattr(self, "sensor_status_var"):
                self.sensor_status_var.set(message)
            return None
        sensor = rows[selection[0]]["name"]
        try:
            self.sensor_filter_var.set(sensor)
        except Exception:
            pass
        message = f"Showing mosaic rows for {sensor}."
        if hasattr(self, "sensor_status_var"):
            self.sensor_status_var.set(message)
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        self.observatory_draw_current_mosaic()
        return sensor



    def observatory_active_sensor_name(self):
        sensor = self.observatory_sensor_filter_name()
        if sensor not in ("", "All sensors"):
            return sensor
        widget = getattr(self, "sensor_summary_list", None)
        if widget is not None:
            try:
                selection = widget.curselection()
            except Exception:
                selection = ()
            rows = self.observatory_sensor_rows()
            if selection and selection[0] < len(rows):
                return rows[selection[0]]["name"]
        for item in self.observatory_sensor_rows():
            if item["products"] or item["observations"]:
                return item["name"]
        return "All sensors"

    def observatory_sensor_product_rows(self, sensor_name=None):
        sensor_name = sensor_name or self.observatory_active_sensor_name()
        rows = list(getattr(self, "product_results", []) or [])
        if sensor_name in ("", "All sensors"):
            return rows
        return [row for row in rows if self.observatory_sensor_family(row) == sensor_name]

    def observatory_sensor_rgb_candidates(self, sensor_name=None):
        candidates = {"blue": [], "green": [], "red": []}
        for row in self.observatory_sensor_product_rows(sensor_name):
            if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                continue
            channel = self.product_rgb_channel(row)
            if channel in candidates:
                candidates[channel].append(row)
        for channel in candidates:
            candidates[channel].sort(key=lambda row: (-self.product_quality_score(row), self.product_sort_key(row)))
        return candidates

    def observatory_sensor_best_rgb_set(self, sensor_name=None):
        sensor_name = sensor_name or self.observatory_active_sensor_name()
        product_rows = self.observatory_sensor_product_rows(sensor_name)
        rgb_sets = self.suggest_rgb_sets_for_rows(product_rows, recipe=self.target_recipe(self.target_var.get())) if product_rows else []
        if rgb_sets:
            return rgb_sets[0]
        candidates = self.observatory_sensor_rgb_candidates(sensor_name)
        if all(candidates[channel] for channel in ("blue", "green", "red")):
            return {channel: candidates[channel][0] for channel in ("blue", "green", "red")}
        return None

    def observatory_sensor_rgb_plan_text(self, sensor_name=None):
        sensor_name = sensor_name or self.observatory_active_sensor_name()
        candidates = self.observatory_sensor_rgb_candidates(sensor_name)
        rgb_set = self.observatory_sensor_best_rgb_set(sensor_name)
        lines = [f"Sensor RGB Plan: {sensor_name}", ""]
        rows = self.observatory_sensor_product_rows(sensor_name)
        lines.append(f"Loaded products for this sensor: {len(rows)}")
        for channel in ("blue", "green", "red"):
            channel_rows = candidates[channel]
            lines.append(f"- {channel.title()} candidates: {len(channel_rows)}")
            if channel_rows:
                lines.append(f"  Best: {self.rgb_candidate_label(channel_rows[0])}")
        lines.append("")
        if rgb_set:
            lines.append("Recommended RGB set:")
            for channel in ("blue", "green", "red"):
                lines.append(f"- {channel.title()}: {self.rgb_candidate_label(rgb_set[channel])}")
            lines.append(f"- Set score: {self.rgb_set_score(rgb_set, self.target_recipe(self.target_var.get()))}")
            lines.append("Use Prepare Sensor RGB to send this set to the RGB Picker.")
        else:
            missing = [channel for channel in ("blue", "green", "red") if not candidates[channel]]
            if rows:
                lines.append("No complete RGB set is available for this sensor yet.")
                lines.append("Missing channels: " + ", ".join(channel.title() for channel in missing))
                lines.append("Try Get All Products, Find Better Sources, or choose a different sensor filter.")
            else:
                lines.append("No products are loaded for this sensor yet. Get products first, then refresh the sensor dashboard.")
        return "\n".join(lines)

    def observatory_show_sensor_rgb_plan(self):
        text = self.observatory_sensor_rgb_plan_text()
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set("Generated sensor RGB plan.")
        self.observatory_update_sensor_dashboard()
        return text

    def observatory_prepare_sensor_rgb_layer(self):
        sensor_name = self.observatory_active_sensor_name()
        rgb_set = self.observatory_sensor_best_rgb_set(sensor_name)
        if not rgb_set:
            message = f"No complete RGB set is available for {sensor_name}. Use Sensor RGB Plan to see missing channels."
            if hasattr(self, "sensor_status_var"):
                self.sensor_status_var.set(message)
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            self.observatory_show_sensor_rgb_plan()
            return False
        self.refresh_product_list()
        for channel in ("blue", "green", "red"):
            self.select_rgb_candidate_row(channel, rgb_set[channel])
        wanted = {id(rgb_set[channel]) for channel in ("blue", "green", "red")}
        try:
            self.product_list.selection_clear(0, "end")
            for index, row in enumerate(self.visible_product_results):
                if id(row) in wanted:
                    self.product_list.selection_set(index)
                    self.product_list.see(index)
        except Exception:
            pass
        try:
            self.notebook.select(self.browser_tab)
        except Exception:
            pass
        message = f"Prepared best {sensor_name} RGB picks. Review the RGB Picker, then download selected RGB channels."
        if hasattr(self, "browser_status"):
            self.browser_status.set(message)
        if hasattr(self, "sensor_status_var"):
            self.sensor_status_var.set(message)
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return True

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
        lines.append("- Sensor families: " + self.observatory_top_counts({
            item["name"]: item["observations"]
            for item in self.observatory_sensor_summary(obs_rows, product_rows).values()
            if item["observations"]
        }, limit=10))
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
        for source_line in composition_strategy_lines(summary):
            lines.append(source_line)
        lines.append("")
        for source_line in composition_readiness_lines(summary):
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
            self.observatory_update_sensor_dashboard()
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



    def observatory_current_summary(self):
        return self.compute_observatory_summary(
            list(getattr(self, "search_results", []) or []),
            list(getattr(self, "product_results", []) or []),
        )


    def observatory_composition_strategy_text(self):
        summary = self.observatory_current_summary()
        target = self.target_var.get().strip() or "(no target)"
        lines = [f"Composition Strategy for {target}", ""]
        lines.extend(composition_strategy_lines(summary))
        return "\n".join(lines)

    def observatory_show_composition_strategy(self):
        text = self.observatory_composition_strategy_text()
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set("Generated multi-telescope composition strategy.")
        return text

    def observatory_composition_readiness_text(self):
        summary = self.observatory_current_summary()
        target = self.target_var.get().strip() or "(no target)"
        lines = [f"Image Build Readiness for {target}", ""]
        lines.extend(composition_readiness_lines(summary))
        return "\n".join(lines)

    def observatory_show_composition_readiness(self):
        text = self.observatory_composition_readiness_text()
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set("Generated image build readiness.")
        return text

    def observatory_project_plan_text(self):
        summary = self.observatory_current_summary()
        target = self.target_var.get().strip() or "(no target)"
        lines = [
            f"Multi-Telescope Project Plan for {target}",
            f"Current telescope setting: {self.telescope_var.get()}",
            f"Current radius: {self.radius_var.get()}",
            "",
        ]
        lines.extend(project_plan_lines(summary))
        return "\n".join(lines)

    def observatory_project_plan_payload(self):
        summary = self.observatory_current_summary()
        return {
            "target": self.current_target_for_log(),
            "summary": summary,
            "project_state": project_state(summary),
            "project_checklist": project_checklist_lines(summary),
            "composition_strategy": composition_strategy_lines(summary),
            "composition_readiness": composition_readiness_state(summary),
            "project_plan": self.observatory_project_plan_text(),
        }

    def observatory_copy_project_plan(self):
        text = self.observatory_project_plan_text()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        message = "Copied multi-telescope project plan to the clipboard."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return text

    def observatory_save_project_plan(self):
        payload = self.observatory_project_plan_payload()
        SEARCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = SEARCH_LOG_DIR / f"{self.current_target_for_log()}_multi_telescope_project_plan.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        message = f"Saved multi-telescope project plan to {path.name}."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return path


    def observatory_latest_project_plan_path(self):
        SEARCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        target = self.current_target_for_log()
        paths = sorted(
            SEARCH_LOG_DIR.glob(f"{target}_multi_telescope_project_plan*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return paths[0] if paths else None

    def observatory_format_loaded_project_plan(self, payload, path=None):
        lines = []
        title_target = payload.get("target", "unknown target") if isinstance(payload, dict) else "unknown target"
        lines.append(f"Loaded Multi-Telescope Project Plan: {title_target}")
        if path is not None:
            lines.append(f"Source file: {path.name}")
        lines.append("")
        plan_text = payload.get("project_plan", "") if isinstance(payload, dict) else ""
        if plan_text:
            lines.append(plan_text)
        else:
            lines.append("No project plan text was found in this saved file.")
        return "\n".join(lines)

    def observatory_load_project_plan(self):
        path = self.observatory_latest_project_plan_path()
        if path is None:
            message = "No saved multi-telescope project plan was found for this target."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            message = f"Could not load project plan: {exc}"
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return None
        text = self.observatory_format_loaded_project_plan(payload, path)
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        message = f"Loaded multi-telescope project plan from {path.name}."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return payload

    def observatory_current_report_text(self):
        widget = getattr(self, "observatory_report_text", None)
        if widget is None:
            return self.observatory_summary_text()
        text = widget.get("1.0", "end").strip()
        if text:
            return text
        return self.observatory_summary_text()

    def observatory_copy_report(self):
        report = self.observatory_current_report_text()
        self.clipboard_clear()
        self.clipboard_append(report)
        self.update()
        message = "Copied Observatory Explorer report to the clipboard."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return report

    def observatory_save_report(self):
        report = self.observatory_current_report_text()
        SEARCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = SEARCH_LOG_DIR / f"{self.current_target_for_log()}_observatory_explorer_report.txt"
        path.write_text(report + "\n", encoding="utf-8")
        message = f"Saved Observatory Explorer report to {path.name}."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return path

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


    def observatory_selected_mosaic_rows(self, rows):
        layer = "All active sources"
        try:
            layer = self.mosaic_layer_var.get()
        except Exception:
            pass
        if layer == "Hubble / HST":
            return [row for row in rows if str(row.get("obs_collection", "")).upper() == "HST"]
        if layer == "JWST":
            return [row for row in rows if str(row.get("obs_collection", "")).upper() == "JWST"]
        return [row for row in rows if str(row.get("obs_collection", "")).upper() in ("HST", "JWST")]

    def observatory_selected_mosaic_label(self):
        try:
            return self.mosaic_layer_var.get()
        except Exception:
            return "All active sources"

    def observatory_mosaic_best_only(self):
        try:
            return bool(self.mosaic_best_only_var.get())
        except Exception:
            return False

    def observatory_mosaic_overlap_only(self):
        try:
            return bool(self.mosaic_overlap_only_var.get())
        except Exception:
            return False

    def observatory_rows_in_bounds(self, rows, bounds):
        if not bounds:
            return []
        selected = []
        for row in rows:
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            if ra is None or dec is None:
                continue
            if bounds["ra_min"] <= ra <= bounds["ra_max"] and bounds["dec_min"] <= dec <= bounds["dec_max"]:
                selected.append(row)
        return selected

    def observatory_hst_jwst_overlap_bounds(self):
        rows = self.observatory_selected_mosaic_rows(list(getattr(self, "search_results", []) or []))
        points = []
        for row in rows:
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            if ra is not None and dec is not None:
                points.append((ra, dec, row))
        bounds = self.observatory_mosaic_bounds_for_points(points)
        if "HST" in bounds and "JWST" in bounds:
            return self.observatory_bounds_overlap(bounds["HST"], bounds["JWST"])
        return None

    def observatory_current_mosaic_rows(self):
        rows = self.observatory_selected_mosaic_rows(list(getattr(self, "search_results", []) or []))
        rows = [row for row in rows if self.observatory_row_matches_sensor_filter(row)]
        if self.observatory_mosaic_best_only():
            rows = self.observatory_best_observations(rows, limit=12)
        if self.observatory_mosaic_overlap_only():
            rows = self.observatory_rows_in_bounds(rows, self.observatory_hst_jwst_overlap_bounds())
        return rows

    def observatory_mosaic_export_rows(self):
        rows = []
        for row in self.observatory_current_mosaic_rows():
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            if ra is None or dec is None:
                continue
            rows.append({
                "obs_collection": row.get("obs_collection", ""),
                "obs_id": row.get("obs_id", "") or row.get("obsid", ""),
                "instrument_name": row.get("instrument_name", ""),
                "filters": row.get("filters", "") or row.get("Spectral_Elt", ""),
                "wavelength_bucket": self.observation_filter_bucket(row),
                "t_exptime": row.get("t_exptime", ""),
                "ra": f"{ra:.8f}",
                "dec": f"{dec:.8f}",
            })
        return rows

    def observatory_copy_mosaic_rows(self):
        rows = self.observatory_mosaic_export_rows()
        if not rows:
            message = "No coordinate-bearing mosaic rows are available to copy."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return ""
        headers = list(rows[0].keys())
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(str(row.get(header, "")) for header in headers))
        text = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        message = f"Copied {len(rows)} mosaic row(s) to the clipboard."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return text

    def observatory_export_mosaic_csv(self):
        rows = self.observatory_mosaic_export_rows()
        if not rows:
            message = "No coordinate-bearing mosaic rows are available to export."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return None

        SEARCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        layer = self.observatory_selected_mosaic_label().lower().replace(" / ", "_").replace(" ", "_")
        if self.observatory_mosaic_best_only():
            layer += "_best_candidates"
        if self.observatory_mosaic_overlap_only():
            layer += "_overlap_candidates"
        path = SEARCH_LOG_DIR / f"{self.current_target_for_log()}_mosaic_{layer}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        message = f"Exported {len(rows)} mosaic row(s) to {path.name}."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return path

    def observatory_mosaic_overlap_candidate_rows(self, limit=16):
        rows = self.observatory_selected_mosaic_rows(list(getattr(self, "search_results", []) or []))
        bounds = self.observatory_hst_jwst_overlap_bounds()
        candidates = self.observatory_rows_in_bounds(rows, bounds)
        if not candidates:
            return []
        return self.observatory_best_observations(candidates, limit=limit)

    def observatory_overlap_candidate_export_rows(self):
        rows = []
        for row in self.observatory_mosaic_overlap_candidate_rows(limit=50):
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            rows.append({
                "obs_collection": row.get("obs_collection", ""),
                "obs_id": row.get("obs_id", "") or row.get("obsid", ""),
                "instrument_name": row.get("instrument_name", ""),
                "filters": row.get("filters", "") or row.get("Spectral_Elt", ""),
                "wavelength_bucket": self.observation_filter_bucket(row),
                "t_exptime": row.get("t_exptime", ""),
                "ra": f"{ra:.8f}" if ra is not None else "",
                "dec": f"{dec:.8f}" if dec is not None else "",
            })
        return rows

    def observatory_copy_overlap_candidates(self):
        rows = self.observatory_overlap_candidate_export_rows()
        if not rows:
            message = "No overlap candidate rows are available to copy."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return ""
        headers = list(rows[0].keys())
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(str(row.get(header, "")) for header in headers))
        text = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        message = f"Copied {len(rows)} overlap candidate row(s) to the clipboard."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return text

    def observatory_export_overlap_candidates_csv(self):
        rows = self.observatory_overlap_candidate_export_rows()
        if not rows:
            message = "No overlap candidate rows are available to export."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return None
        SEARCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = SEARCH_LOG_DIR / f"{self.current_target_for_log()}_mosaic_overlap_candidates.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        message = f"Exported {len(rows)} overlap candidate row(s) to {path.name}."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return path

    def observatory_mosaic_overlap_candidates_text(self):
        bounds = self.observatory_hst_jwst_overlap_bounds()
        target = self.target_var.get().strip() if hasattr(self, "target_var") else ""
        title_target = target or "current target"
        lines = [f"Overlap Candidates for {title_target}", ""]
        if not bounds:
            lines.append("No shared Hubble/JWST overlap area was found in the current mosaic rows.")
            lines.append("Try searching both Hubble and JWST, widening the radius, or turning off Best candidates only.")
            return "\n".join(lines)
        lines.append(
            f"Shared area: RA {bounds['ra_min']:.6f} to {bounds['ra_max']:.6f}, "
            f"Dec {bounds['dec_min']:.6f} to {bounds['dec_max']:.6f}."
        )
        candidates = self.observatory_mosaic_overlap_candidate_rows()
        if not candidates:
            lines.append("No observation centers fall inside the shared area yet.")
            return "\n".join(lines)
        lines.append(f"Candidate observations inside overlap: {len(candidates)}")
        lines.append("")
        for index, row in enumerate(candidates, start=1):
            lines.append(f"{index}. {self.observatory_observation_label(row)}")
        lines.append("")
        lines.append("Suggested next steps:")
        lines.append("- Turn on Overlap only to inspect these markers on the mosaic.")
        lines.append("- Click the strongest Hubble/JWST markers and use Get Marker Products.")
        lines.append("- Prefer rows with useful filters, longer exposure, and matching sky coverage before composing.")
        return "\n".join(lines)

    def observatory_show_overlap_candidates(self):
        text = self.observatory_mosaic_overlap_candidates_text()
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            count = len(self.observatory_mosaic_overlap_candidate_rows())
            self.mosaic_status_var.set(f"Found {count} overlap candidate observation(s).")
        return text

    def observatory_select_best_overlap_candidate(self):
        candidates = self.observatory_mosaic_overlap_candidate_rows(limit=1)
        if not candidates:
            message = "No overlap candidate is available to select. Try searching both Hubble and JWST or widening the radius."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return None
        row = candidates[0]
        self.selected_mosaic_row = row
        self.observatory_select_observation_row(row)
        try:
            self.mosaic_overlap_only_var.set(True)
        except Exception:
            pass
        detail = self.observatory_mosaic_marker_detail(row)
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", "Best Overlap Candidate\n\n" + detail)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            obs_id = row.get("obs_id", "") or row.get("obsid", "") or "selected observation"
            self.mosaic_status_var.set(f"Selected best overlap candidate: {obs_id}. Use Get Marker Products next.")
        self.observatory_draw_current_mosaic()
        return row

    def observatory_mosaic_marker_detail(self, row):
        ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
        dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
        ra_text = f"{ra:.6f}" if ra is not None else "not listed"
        dec_text = f"{dec:.6f}" if dec is not None else "not listed"
        return "\n".join([
            "Selected Mosaic Observation:",
            f"- Mission: {row.get('obs_collection', '') or 'Unknown'}",
            f"- Observation ID: {row.get('obs_id', '') or row.get('obsid', '') or 'unknown'}",
            f"- Instrument: {row.get('instrument_name', '') or 'Unknown'}",
            f"- Filter: {row.get('filters', '') or row.get('Spectral_Elt', '') or 'not listed'}",
            f"- Exposure: {row.get('t_exptime', '') or '?'} seconds",
            f"- RA/Dec: {ra_text}, {dec_text}",
            f"- Wavelength bucket: {self.observation_filter_bucket(row)}",
        ])

    def observatory_mosaic_row_matches(self, left, right):
        for key in ("obs_id", "obsid", "obsID"):
            left_value = str(left.get(key, "") or "")
            right_value = str(right.get(key, "") or "")
            if left_value and right_value and left_value == right_value:
                return True
        return left is right

    def observatory_select_observation_row(self, row):
        widget = getattr(self, "obs_list", None)
        if widget is None:
            return False
        for index, candidate in enumerate(list(getattr(self, "search_results", []) or [])[:500]):
            if self.observatory_mosaic_row_matches(row, candidate):
                widget.selection_clear(0, "end")
                widget.selection_set(index)
                widget.see(index)
                return True
        return False

    def observatory_mosaic_click(self, event):
        markers = list(getattr(self, "mosaic_marker_points", []) or [])
        if not markers:
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set("No mosaic marker is available to select yet.")
            return None
        nearest = None
        nearest_distance = None
        for marker in markers:
            distance = math.hypot(event.x - marker["x"], event.y - marker["y"])
            if nearest is None or distance < nearest_distance:
                nearest = marker
                nearest_distance = distance
        if nearest is None or nearest_distance > max(14, nearest.get("size", 4) + 8):
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set("Click closer to a mosaic marker to select an observation.")
            return None
        row = nearest["row"]
        detail = self.observatory_mosaic_marker_detail(row)
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(detail.replace("\n", " "))
        try:
            self.observatory_report_text.insert("end", "\n\n" + detail)
            self.observatory_report_text.see("end")
        except Exception:
            pass
        self.selected_mosaic_row = row
        self.observatory_select_observation_row(row)
        self.observatory_draw_current_mosaic()
        return row

    def observatory_copy_marker_details(self):
        row = getattr(self, "selected_mosaic_row", None)
        if row is None:
            message = "Click a mosaic marker first, then copy marker details."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return ""
        detail = self.observatory_mosaic_marker_detail(row)
        self.clipboard_clear()
        self.clipboard_append(detail)
        self.update()
        message = "Copied selected mosaic marker details to the clipboard."
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set(message)
        return detail

    def observatory_get_marker_products(self):
        row = getattr(self, "selected_mosaic_row", None)
        if row is None:
            message = "Click a mosaic marker first, then use Get Marker Products."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return False
        if not self.observatory_select_observation_row(row):
            message = "The selected mosaic marker is not available in the current observation list."
            if hasattr(self, "mosaic_status_var"):
                self.mosaic_status_var.set(message)
            return False
        try:
            self.notebook.select(self.browser_tab)
        except Exception:
            pass
        self.products_async()
        return True

    @staticmethod
    def observatory_mosaic_bounds_for_points(points):
        bounds = {}
        for ra, dec, row in points:
            mission = str(row.get("obs_collection", "Unknown") or "Unknown").upper()
            current = bounds.setdefault(mission, {
                "mission": mission,
                "count": 0,
                "ra_min": ra,
                "ra_max": ra,
                "dec_min": dec,
                "dec_max": dec,
            })
            current["count"] += 1
            current["ra_min"] = min(current["ra_min"], ra)
            current["ra_max"] = max(current["ra_max"], ra)
            current["dec_min"] = min(current["dec_min"], dec)
            current["dec_max"] = max(current["dec_max"], dec)
        return bounds

    @staticmethod
    def observatory_bounds_overlap(left, right):
        ra_min = max(left["ra_min"], right["ra_min"])
        ra_max = min(left["ra_max"], right["ra_max"])
        dec_min = max(left["dec_min"], right["dec_min"])
        dec_max = min(left["dec_max"], right["dec_max"])
        if ra_max < ra_min or dec_max < dec_min:
            return None
        return {
            "ra_min": ra_min,
            "ra_max": ra_max,
            "dec_min": dec_min,
            "dec_max": dec_max,
            "ra_span": ra_max - ra_min,
            "dec_span": dec_max - dec_min,
        }

    def observatory_mosaic_coverage_summary(self):
        points = []
        for row in self.observatory_current_mosaic_rows():
            ra = self.numeric_row_value(row, "s_ra", "ra", "RA")
            dec = self.numeric_row_value(row, "s_dec", "dec", "DEC")
            if ra is not None and dec is not None:
                points.append((ra, dec, row))
        bounds = self.observatory_mosaic_bounds_for_points(points)
        overlap = None
        if "HST" in bounds and "JWST" in bounds:
            overlap = self.observatory_bounds_overlap(bounds["HST"], bounds["JWST"])
        return {
            "points": len(points),
            "bounds": bounds,
            "hst_jwst_overlap": overlap,
            "layer": self.observatory_selected_mosaic_label(),
            "best_only": self.observatory_mosaic_best_only(),
            "overlap_only": self.observatory_mosaic_overlap_only(),
        }

    def observatory_mosaic_coverage_text(self):
        summary = self.observatory_mosaic_coverage_summary()
        layer = summary["layer"]
        if summary["best_only"]:
            layer = f"{layer} - best candidates"
        if summary.get("overlap_only"):
            layer = f"{layer} - overlap candidates"
        lines = [f"Mosaic Coverage Summary for {layer}", ""]
        lines.append(f"Coordinate-bearing observations: {summary['points']}")
        if not summary["bounds"]:
            lines.append("- No coordinate-bearing observations are available yet.")
            lines.append("- Run a search or widen the radius, then build the mosaic again.")
            return "\n".join(lines)
        lines.append("Mission coverage boxes:")
        for mission, bounds in sorted(summary["bounds"].items()):
            lines.append(
                f"- {mission}: {bounds['count']} point(s), "
                f"RA {bounds['ra_min']:.6f} to {bounds['ra_max']:.6f}, "
                f"Dec {bounds['dec_min']:.6f} to {bounds['dec_max']:.6f}."
            )
        overlap = summary["hst_jwst_overlap"]
        lines.append("")
        lines.append("Hubble/JWST overlap:")
        if overlap:
            lines.append(
                f"- Overlap found: RA {overlap['ra_min']:.6f} to {overlap['ra_max']:.6f}, "
                f"Dec {overlap['dec_min']:.6f} to {overlap['dec_max']:.6f}."
            )
            lines.append("- This is a promising area for a combined Hubble plus JWST composition.")
        elif "HST" in summary["bounds"] and "JWST" in summary["bounds"]:
            lines.append("- Hubble and JWST coordinate boxes do not overlap in the current mosaic selection.")
            lines.append("- Try Search Wider Radius or switch off Best candidates only to inspect more coverage.")
        else:
            lines.append("- Load both Hubble and JWST coordinate-bearing observations to estimate overlap.")
        return "\n".join(lines)

    def observatory_show_mosaic_coverage(self):
        text = self.observatory_mosaic_coverage_text()
        try:
            self.observatory_report_text.delete("1.0", "end")
            self.observatory_report_text.insert("end", text)
        except Exception:
            pass
        if hasattr(self, "mosaic_status_var"):
            self.mosaic_status_var.set("Generated mosaic coverage summary.")
        self.observatory_draw_current_mosaic()
        return text

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
        self.mosaic_marker_points = []
        width = max(400, int(canvas.winfo_width() or 700))
        height = max(300, int(canvas.winfo_height() or 500))
        rows = self.observatory_current_mosaic_rows()
        layer_label = self.observatory_selected_mosaic_label()
        best_only = self.observatory_mosaic_best_only()
        if best_only:
            layer_label = f"{layer_label} - best candidates"
        if self.observatory_mosaic_overlap_only():
            layer_label = f"{layer_label} - overlap candidates"
        sensor_filter = self.observatory_sensor_filter_name()
        if sensor_filter not in ("", "All sensors"):
            layer_label = f"{layer_label} - {sensor_filter}"
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

        canvas.create_text(width // 2, 22, text=f"Sky Mosaic / Coverage Map - {layer_label}", fill="#ffffff", font=("Segoe UI", 14, "bold"))
        if not points:
            canvas.create_text(
                width // 2,
                height // 2,
                text=f"No observation coordinates loaded for {layer_label}.\nRun Search MAST, Search Wider Radius, or Find Better Sources.",
                fill="#ffffff",
                font=("Segoe UI", 11),
                justify="center",
            )
            self.mosaic_status_var.set(f"No coordinate-bearing observations available for {layer_label}.")
            self.observatory_update_sensor_dashboard()
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
        guide_text = "Marker size hints exposure time; color hints likely wavelength bucket."
        if best_only:
            guide_text = "Showing the strongest observation candidates by coordinates, exposure, wavelength, and mission."
        canvas.create_text(plot_x0, 38, anchor="w", text=guide_text, fill="#d1d5db")

        mission_box_colors = {"HST": "#93c5fd", "JWST": "#67e8f9"}
        for mission, bounds in self.observatory_mosaic_bounds_for_points(points).items():
            if bounds["count"] < 2:
                continue
            x0, y_bottom = map_point(bounds["ra_min"], bounds["dec_min"])
            x1, y_top = map_point(bounds["ra_max"], bounds["dec_max"])
            color = mission_box_colors.get(mission, "#9ca3af")
            canvas.create_rectangle(min(x0, x1), min(y_top, y_bottom), max(x0, x1), max(y_top, y_bottom), outline=color, width=2, dash=(6, 4))
            canvas.create_text(min(x0, x1) + 6, min(y_top, y_bottom) + 10, anchor="w", text=f"{mission} coverage", fill=color, font=("Segoe UI", 8, "bold"))

        overlap = None
        bounds = self.observatory_mosaic_bounds_for_points(points)
        if "HST" in bounds and "JWST" in bounds:
            overlap = self.observatory_bounds_overlap(bounds["HST"], bounds["JWST"])
        if overlap:
            x0, y_bottom = map_point(overlap["ra_min"], overlap["dec_min"])
            x1, y_top = map_point(overlap["ra_max"], overlap["dec_max"])
            canvas.create_rectangle(min(x0, x1), min(y_top, y_bottom), max(x0, x1), max(y_top, y_bottom), outline="#facc15", width=3)
            canvas.create_text(max(x0, x1) - 6, max(y_top, y_bottom) - 10, anchor="e", text="HST/JWST overlap", fill="#facc15", font=("Segoe UI", 8, "bold"))

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
            if self.observatory_mosaic_row_matches(row, getattr(self, "selected_mosaic_row", {})):
                canvas.create_oval(x - size - 4, y - size - 4, x + size + 4, y + size + 4, outline="#facc15", width=3)
                canvas.create_text(x, y - size - 12, text="selected", fill="#facc15", font=("Segoe UI", 8, "bold"))
            self.mosaic_marker_points.append({"x": x, "y": y, "size": size, "row": row})

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
        selected_note = ""
        selected_row = getattr(self, "selected_mosaic_row", None)
        if selected_row is not None and any(self.observatory_mosaic_row_matches(marker["row"], selected_row) for marker in self.mosaic_marker_points):
            selected_note = " Selected marker is highlighted."
        self.mosaic_status_var.set(
            f"Plotted {len(points)} observation centers for {layer_label}. Missions: {mission_text}. Wavelength buckets: {bucket_text}."
            f"{selected_note} True footprint polygons remain a later Phase 2 upgrade."
        )
        self.observatory_update_sensor_dashboard()

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
