import unittest

from hubble_workbench_app.observatory_sources import (
    layer_readiness_line,
    composition_readiness_lines,
    composition_readiness_state,
    planned_activation_lines,
    composition_strategy_lines,
    project_checklist_lines,
    project_plan_lines,
    project_state,
    source_layer_state,
    source_observation_count,
    source_product_count,
    source_rgb_counts,
)


class ObservatorySourceTests(unittest.TestCase):
    def test_source_observation_count_matches_known_codes(self):
        summary = {"by_mission": {"HST": 3, "JWST": 2, "Other": 1}}
        self.assertEqual(source_observation_count(summary, {"name": "Hubble", "code": "HST"}), 3)
        self.assertEqual(source_observation_count(summary, {"name": "James Webb", "code": "JWST"}), 2)

    def test_source_product_and_rgb_counts_match_known_codes(self):
        summary = {
            "products_by_mission": {"HST": 4, "JWST": 2},
            "channels_by_mission": {
                "HST": {"blue": 1, "green": 1, "red": 0},
                "JWST": {"blue": 0, "green": 1, "red": 1},
            },
        }
        hubble = {"name": "Hubble", "code": "HST"}
        self.assertEqual(source_product_count(summary, hubble), 4)
        self.assertEqual(source_rgb_counts(summary, hubble), {"blue": 1, "green": 1, "red": 0})

    def test_source_layer_state_is_structured_for_saved_project_data(self):
        summary = {
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 4},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 1}},
        }
        state = source_layer_state(summary, {"name": "Hubble", "code": "HST", "kind": "space telescope", "status": "active", "role": "Visible"})
        self.assertEqual(state["observations"], 3)
        self.assertEqual(state["products"], 4)
        self.assertTrue(state["rgb_complete"])
        self.assertEqual(state["next_action"], "ready for RGB review")

    def test_project_state_groups_active_and_planned_sources(self):
        summary = {
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 4},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 1}},
        }
        state = project_state(summary)
        self.assertEqual(state["active_with_observations"], 1)
        self.assertEqual(state["active_ready_for_rgb"], 1)
        self.assertGreaterEqual(len(state["planned_sources"]), 3)

    def test_layer_readiness_names_next_step(self):
        summary = {
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 4},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 0}},
        }
        line = layer_readiness_line(summary, {"name": "Hubble", "code": "HST", "kind": "space telescope", "status": "active", "role": "Visible"})
        self.assertIn("products=4", line)
        self.assertIn("RGB blue=1, green=1, red=0", line)
        self.assertIn("missing red coverage", line)

    def test_planned_sources_explain_activation_requirements(self):
        report = "\n".join(planned_activation_lines())
        self.assertIn("Chandra (CHANDRA)", report)
        self.assertIn("archive search", report)
        self.assertIn("Pan-STARRS (PANSTARRS)", report)
        self.assertIn("survey cutout", report)
        self.assertIn("DSS (DSS)", report)
        self.assertIn("reference image", report)


    def test_composition_readiness_scores_ready_layer(self):
        summary = {
            "observations": 4,
            "products": 8,
            "by_mission": {"HST": 4},
            "products_by_mission": {"HST": 8},
            "channels_by_mission": {"HST": {"blue": 2, "green": 2, "red": 1}},
            "enhanced_products": 2,
        }
        readiness = composition_readiness_state(summary)
        report = "\n".join(composition_readiness_lines(summary))
        self.assertGreaterEqual(readiness["score"], 85)
        self.assertEqual(readiness["best_source"]["name"], "Hubble")
        self.assertIn("Image Build Readiness:", report)
        self.assertIn("Best starting layer: Hubble", report)

    def test_composition_strategy_prefers_ready_rgb_layers(self):
        summary = {
            "observations": 3,
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 6},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 1}},
        }
        report = "\n".join(composition_strategy_lines(summary))
        self.assertIn("Composition Strategy:", report)
        self.assertIn("Build the first polished RGB layer", report)
        self.assertIn("Hubble", report)

    def test_project_checklist_names_immediate_actions(self):
        empty_lines = project_checklist_lines({"observations": 0})
        self.assertIn("Search Hubble or JWST", "\n".join(empty_lines))

        summary = {
            "observations": 3,
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 4},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 0}},
        }
        lines = project_checklist_lines(summary)
        report = "\n".join(lines)
        self.assertIn("Improve Hubble RGB coverage", report)
        self.assertIn("missing red", report)
        self.assertIn("Build at least one complete", report)





    def test_loaded_project_plan_format_includes_saved_text(self):
        from pathlib import Path
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Dummy(ObservatoryWorkflowMixin):
            pass

        text = Dummy().observatory_format_loaded_project_plan(
            {"target": "M51", "project_plan": "Saved plan body"},
            Path("M51_multi_telescope_project_plan.json"),
        )
        self.assertIn("Loaded Multi-Telescope Project Plan: M51", text)
        self.assertIn("M51_multi_telescope_project_plan.json", text)
        self.assertIn("Saved plan body", text)

    def test_project_plan_text_contains_project_sections(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Dummy(ObservatoryWorkflowMixin):
            search_results = []
            product_results = []
            target_var = Var("M51")
            telescope_var = Var("Hubble / HST")
            radius_var = Var("0.05 deg")

            def current_target_for_log(self):
                return "M51"

            def compute_observatory_summary(self, obs_rows=None, product_rows=None):
                return {"observations": 0, "by_mission": {}, "products_by_mission": {}, "channels_by_mission": {}}

        text = Dummy().observatory_project_plan_text()
        self.assertIn("Multi-Telescope Project Plan for M51", text)
        self.assertIn("Active search sources:", text)
        self.assertIn("Planned context layers:", text)

    def test_copy_marker_details_requires_selection(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Status:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class Dummy(ObservatoryWorkflowMixin):
            pass

        app = Dummy()
        app.mosaic_status_var = Status()
        self.assertEqual(app.observatory_copy_marker_details(), "")
        self.assertIn("Click a mosaic marker first", app.mosaic_status_var.value)

    def test_marker_products_requires_selected_marker(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Status:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class Dummy(ObservatoryWorkflowMixin):
            pass

        app = Dummy()
        app.mosaic_status_var = Status()
        self.assertFalse(app.observatory_get_marker_products())
        self.assertIn("Click a mosaic marker first", app.mosaic_status_var.value)

    def test_mosaic_marker_detail_includes_observation_fields(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Dummy(ObservatoryWorkflowMixin):
            def observation_filter_bucket(self, row):
                return "Blue/short wavelength"

        detail = Dummy().observatory_mosaic_marker_detail({
            "obs_collection": "HST",
            "obs_id": "obs-1",
            "instrument_name": "WFC3",
            "filters": "F555W",
            "t_exptime": "1200",
            "s_ra": "1.5",
            "s_dec": "-2.25",
        })
        self.assertIn("Selected Mosaic Observation", detail)
        self.assertIn("obs-1", detail)
        self.assertIn("1.500000, -2.250000", detail)
        self.assertIn("Blue/short wavelength", detail)

    def test_mosaic_coverage_summary_finds_hubble_jwst_overlap(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def get(self):
                return "All active sources"

        class Dummy(ObservatoryWorkflowMixin):
            search_results = [
                {"obs_collection": "HST", "obs_id": "h1", "s_ra": "10.0", "s_dec": "20.0"},
                {"obs_collection": "HST", "obs_id": "h2", "s_ra": "10.2", "s_dec": "20.2"},
                {"obs_collection": "JWST", "obs_id": "j1", "s_ra": "10.1", "s_dec": "20.1"},
                {"obs_collection": "JWST", "obs_id": "j2", "s_ra": "10.3", "s_dec": "20.3"},
            ]
            mosaic_layer_var = Var()

            def observatory_mosaic_best_only(self):
                return False

        summary = Dummy().observatory_mosaic_coverage_summary()
        report = Dummy().observatory_mosaic_coverage_text()
        self.assertEqual(summary["points"], 4)
        self.assertIsNotNone(summary["hst_jwst_overlap"])
        self.assertIn("Overlap found", report)

    def test_mosaic_export_rows_include_coordinates(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Dummy(ObservatoryWorkflowMixin):
            search_results = [{"obs_collection": "HST", "obs_id": "o1", "s_ra": "1.25", "s_dec": "-2.5"}]

            def observatory_mosaic_best_only(self):
                return False

            def observatory_selected_mosaic_rows(self, rows):
                return rows

            def observation_filter_bucket(self, row):
                return "Unknown/other"

        rows = Dummy().observatory_mosaic_export_rows()
        self.assertEqual(rows[0]["ra"], "1.25000000")
        self.assertEqual(rows[0]["dec"], "-2.50000000")
        self.assertEqual(rows[0]["obs_id"], "o1")

    def test_select_best_overlap_candidate_sets_selected_row(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def __init__(self, value=False):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Status:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class Dummy(ObservatoryWorkflowMixin):
            search_results = [
                {"obs_collection": "HST", "obs_id": "h1", "instrument_name": "WFC3", "filters": "F555W", "t_exptime": "900", "s_ra": "10.0", "s_dec": "20.0"},
                {"obs_collection": "HST", "obs_id": "h2", "instrument_name": "WFC3", "filters": "F814W", "t_exptime": "1500", "s_ra": "10.2", "s_dec": "20.2"},
                {"obs_collection": "JWST", "obs_id": "j1", "instrument_name": "NIRCam", "filters": "F200W", "t_exptime": "1200", "s_ra": "10.1", "s_dec": "20.1"},
                {"obs_collection": "JWST", "obs_id": "j2", "instrument_name": "NIRCam", "filters": "F444W", "t_exptime": "1100", "s_ra": "10.3", "s_dec": "20.3"},
            ]
            mosaic_layer_var = Var("All active sources")
            mosaic_overlap_only_var = Var(False)

            def observatory_mosaic_best_only(self):
                return False

            def observatory_select_observation_row(self, row):
                self.selected_from_list = row
                return True

            def observatory_draw_current_mosaic(self):
                self.drew_mosaic = True

        app = Dummy()
        app.mosaic_status_var = Status()
        row = app.observatory_select_best_overlap_candidate()
        self.assertIsNotNone(row)
        self.assertEqual(app.selected_mosaic_row, row)
        self.assertTrue(app.mosaic_overlap_only_var.get())
        self.assertTrue(app.drew_mosaic)
        self.assertIn("Get Marker Products", app.mosaic_status_var.value)

    def test_select_best_overlap_candidate_handles_empty_list(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Status:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class Dummy(ObservatoryWorkflowMixin):
            search_results = []

        app = Dummy()
        app.mosaic_status_var = Status()
        self.assertIsNone(app.observatory_select_best_overlap_candidate())
        self.assertIn("No overlap candidate", app.mosaic_status_var.value)

    def test_overlap_candidate_export_rows_include_shared_area_fields(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Dummy(ObservatoryWorkflowMixin):
            search_results = [
                {"obs_collection": "HST", "obs_id": "h1", "instrument_name": "WFC3", "filters": "F555W", "t_exptime": "900", "s_ra": "10.0", "s_dec": "20.0"},
                {"obs_collection": "HST", "obs_id": "h2", "instrument_name": "WFC3", "filters": "F814W", "t_exptime": "1500", "s_ra": "10.2", "s_dec": "20.2"},
                {"obs_collection": "JWST", "obs_id": "j1", "instrument_name": "NIRCam", "filters": "F200W", "t_exptime": "1200", "s_ra": "10.1", "s_dec": "20.1"},
                {"obs_collection": "JWST", "obs_id": "j2", "instrument_name": "NIRCam", "filters": "F444W", "t_exptime": "1100", "s_ra": "10.3", "s_dec": "20.3"},
            ]
            mosaic_layer_var = Var("All active sources")

            def observatory_mosaic_best_only(self):
                return False

        rows = Dummy().observatory_overlap_candidate_export_rows()
        self.assertEqual({row["obs_id"] for row in rows}, {"h2", "j1"})
        self.assertEqual(rows[0]["ra"].count("."), 1)
        self.assertIn("wavelength_bucket", rows[0])

    def test_mosaic_overlap_candidates_report_lists_shared_rows(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Dummy(ObservatoryWorkflowMixin):
            search_results = [
                {"obs_collection": "HST", "obs_id": "h1", "instrument_name": "WFC3", "filters": "F555W", "t_exptime": "900", "s_ra": "10.0", "s_dec": "20.0"},
                {"obs_collection": "HST", "obs_id": "h2", "instrument_name": "WFC3", "filters": "F814W", "t_exptime": "1500", "s_ra": "10.2", "s_dec": "20.2"},
                {"obs_collection": "JWST", "obs_id": "j1", "instrument_name": "NIRCam", "filters": "F200W", "t_exptime": "1200", "s_ra": "10.1", "s_dec": "20.1"},
                {"obs_collection": "JWST", "obs_id": "j2", "instrument_name": "NIRCam", "filters": "F444W", "t_exptime": "1100", "s_ra": "10.3", "s_dec": "20.3"},
            ]
            mosaic_layer_var = Var("All active sources")
            target_var = Var("M51")

            def observatory_mosaic_best_only(self):
                return False

        app = Dummy()
        report = app.observatory_mosaic_overlap_candidates_text()
        self.assertIn("Overlap Candidates for M51", report)
        self.assertIn("h2", report)
        self.assertIn("j1", report)
        self.assertNotIn("h1", report)
        self.assertIn("Get Marker Products", report)

    def test_mosaic_overlap_only_keeps_shared_area_rows(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Dummy(ObservatoryWorkflowMixin):
            search_results = [
                {"obs_collection": "HST", "obs_id": "h1", "s_ra": "10.0", "s_dec": "20.0"},
                {"obs_collection": "HST", "obs_id": "h2", "s_ra": "10.2", "s_dec": "20.2"},
                {"obs_collection": "JWST", "obs_id": "j1", "s_ra": "10.1", "s_dec": "20.1"},
                {"obs_collection": "JWST", "obs_id": "j2", "s_ra": "10.3", "s_dec": "20.3"},
            ]
            mosaic_layer_var = Var("All active sources")
            mosaic_overlap_only_var = Var(True)

            def observatory_mosaic_best_only(self):
                return False

        rows = Dummy().observatory_current_mosaic_rows()
        self.assertEqual([row["obs_id"] for row in rows], ["h2", "j1"])

    def test_mosaic_rows_respect_layer_filter(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Dummy(ObservatoryWorkflowMixin):
            pass

        app = Dummy()
        app.mosaic_layer_var = Var("JWST")
        rows = [{"obs_collection": "HST"}, {"obs_collection": "JWST"}]
        self.assertEqual(app.observatory_selected_mosaic_rows(rows), [{"obs_collection": "JWST"}])

    def test_observatory_report_text_falls_back_to_summary(self):
        from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

        class Dummy(ObservatoryWorkflowMixin):
            def observatory_summary_text(self):
                return "fallback report"

        self.assertEqual(Dummy().observatory_current_report_text(), "fallback report")

    def test_project_plan_marks_loaded_and_planned_sources(self):
        summary = {
            "observations": 3,
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 4},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 0}},
        }
        lines = project_plan_lines(summary)
        report = "\n".join(lines)
        self.assertIn("Active search sources:", report)
        self.assertIn("Layer readiness:", report)
        self.assertIn("Project checklist:", report)
        self.assertIn("Hubble (HST)", report)
        self.assertIn("current observations loaded: 3", report)
        self.assertIn("Planned context layers:", report)
        self.assertIn("Chandra (CHANDRA)", report)
        self.assertIn("[planned]", report)
        self.assertIn("Activation needed:", report)


from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin


class SensorWorkflowHarness(ObservatoryWorkflowMixin):
    def product_rgb_channel(self, row):
        text = str(row.get("filters", "") or row.get("Spectral_Elt", "")).upper()
        if "F438W" in text or "F090W" in text:
            return "blue"
        if "F555W" in text or "F200W" in text:
            return "green"
        if "F814W" in text or "F444W" in text:
            return "red"
        return None

    def product_is_direct_fits(self, row):
        return str(row.get("productFilename", "")).lower().endswith((".fits", ".fits.gz")) or "fits" in str(row.get("Format", "")).lower()

    def product_is_spectrum(self, row):
        return False

    def product_sort_key(self, row):
        return str(row.get("productFilename", ""))

    def product_quality_score(self, row):
        return 1

    def rgb_candidate_label(self, row):
        return f"{row.get('Spectral_Elt', '') or row.get('filters', '')} | {row.get('productFilename', '')}"

    def target_recipe(self, target):
        return None

    def rgb_set_score(self, rgb_set, recipe=None):
        return 3

    def suggest_rgb_sets_for_rows(self, rows, recipe=None):
        candidates = {"blue": [], "green": [], "red": []}
        for row in rows:
            channel = self.product_rgb_channel(row)
            if channel:
                candidates[channel].append(row)
        if all(candidates[channel] for channel in ("blue", "green", "red")):
            return [{channel: candidates[channel][0] for channel in ("blue", "green", "red")}]
        return []


class ObservatorySensorCoverageTests(unittest.TestCase):
    def test_sensor_family_detects_hubble_and_jwst_instruments(self):
        workflow = SensorWorkflowHarness()
        self.assertEqual(workflow.observatory_sensor_family({"obs_collection": "HST", "instrument_name": "WFC3/UVIS"}), "WFC3 UVIS")
        self.assertEqual(workflow.observatory_sensor_family({"obs_collection": "HST", "instrument_name": "ACS/WFC"}), "ACS WFC")
        self.assertEqual(workflow.observatory_sensor_family({"obs_collection": "JWST", "instrument_name": "NIRCam"}), "NIRCam")
        self.assertEqual(workflow.observatory_sensor_family({"obs_collection": "JWST", "instrument_name": "MIRI"}), "MIRI")

    def test_sensor_summary_counts_observations_products_and_rgb_channels(self):
        workflow = SensorWorkflowHarness()
        observations = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "filters": "F438W", "t_exptime": "100", "s_ra": "10", "s_dec": "20"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "filters": "F555W", "t_exptime": "200", "s_ra": "11", "s_dec": "21"},
            {"obs_collection": "JWST", "instrument_name": "NIRCam", "filters": "F444W", "t_exptime": "300"},
        ]
        products = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "filters": "F438W"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "filters": "F555W"},
            {"obs_collection": "JWST", "instrument_name": "NIRCam", "filters": "F444W"},
        ]
        summary = workflow.observatory_sensor_summary(observations, products)
        self.assertEqual(summary["WFC3 UVIS"]["observations"], 2)
        self.assertEqual(summary["WFC3 UVIS"]["coordinates"], 2)
        self.assertEqual(summary["WFC3 UVIS"]["products"], 2)
        self.assertEqual(summary["WFC3 UVIS"]["channels"], {"blue": 1, "green": 1, "red": 0})
        self.assertEqual(summary["NIRCam"]["observations"], 1)
        self.assertEqual(summary["NIRCam"]["channels"]["red"], 1)


    def test_sensor_rgb_plan_recommends_complete_set(self):
        workflow = SensorWorkflowHarness()
        workflow.product_results = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F438W", "Spectral_Elt": "F438W", "productFilename": "target_blue_drc.fits", "Format": "image/fits", "size": "1000000"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F555W", "Spectral_Elt": "F555W", "productFilename": "target_green_drc.fits", "Format": "image/fits", "size": "1000000"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F814W", "Spectral_Elt": "F814W", "productFilename": "target_red_drc.fits", "Format": "image/fits", "size": "1000000"},
        ]
        workflow.target_var = type("Var", (), {"get": lambda self: "M51"})()
        workflow.sensor_filter_var = type("Var", (), {"get": lambda self: "WFC3 UVIS"})()
        rgb_set = workflow.observatory_sensor_best_rgb_set("WFC3 UVIS")
        self.assertIsNotNone(rgb_set)
        self.assertEqual(rgb_set["blue"]["Spectral_Elt"], "F438W")
        self.assertIn("Recommended RGB set", workflow.observatory_sensor_rgb_plan_text("WFC3 UVIS"))

    def test_sensor_rgb_plan_reports_missing_channels(self):
        workflow = SensorWorkflowHarness()
        workflow.product_results = [
            {"obs_collection": "JWST", "instrument_name": "NIRCam", "Detector": "NIRCam", "filters": "F090W", "Spectral_Elt": "F090W", "productFilename": "jwst_blue_i2d.fits", "Format": "image/fits"},
        ]
        workflow.target_var = type("Var", (), {"get": lambda self: "M16"})()
        plan = workflow.observatory_sensor_rgb_plan_text("NIRCam")
        self.assertIn("No complete RGB set", plan)
        self.assertIn("Green", plan)
        self.assertIn("Red", plan)

    def test_sensor_export_rows_include_rgb_recommendation(self):
        workflow = SensorWorkflowHarness()
        workflow.product_results = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F438W", "Spectral_Elt": "F438W", "productFilename": "target_blue_drc.fits", "Format": "image/fits", "size": "1000000"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F555W", "Spectral_Elt": "F555W", "productFilename": "target_green_drc.fits", "Format": "image/fits", "size": "1000000"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F814W", "Spectral_Elt": "F814W", "productFilename": "target_red_drc.fits", "Format": "image/fits", "size": "1000000"},
        ]
        workflow.search_results = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "filters": "F438W", "s_ra": "1", "s_dec": "2", "t_exptime": "100"},
        ]
        workflow.target_var = type("Var", (), {"get": lambda self: "M51"})()
        rows = workflow.observatory_sensor_export_rows()
        wfc3 = next(row for row in rows if row["sensor"] == "WFC3 UVIS")
        self.assertTrue(wfc3["rgb_complete"])
        self.assertEqual(wfc3["best_rgb_score"], 3)
        self.assertEqual(wfc3["best_blue"], "target_blue_drc.fits")
        self.assertIn("best_green", workflow.observatory_sensor_export_text())


    def test_sensor_readiness_ranks_complete_rgb_sensor_first(self):
        workflow = SensorWorkflowHarness()
        workflow.product_results = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F438W", "Spectral_Elt": "F438W", "productFilename": "uvis_blue.fits", "Format": "image/fits"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F555W", "Spectral_Elt": "F555W", "productFilename": "uvis_green.fits", "Format": "image/fits"},
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F814W", "Spectral_Elt": "F814W", "productFilename": "uvis_red.fits", "Format": "image/fits"},
            {"obs_collection": "JWST", "instrument_name": "NIRCam", "Detector": "NIRCam", "filters": "F090W", "Spectral_Elt": "F090W", "productFilename": "nircam_blue.fits", "Format": "image/fits"},
        ]
        workflow.search_results = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "filters": "F438W", "s_ra": "1", "s_dec": "2", "t_exptime": "100"},
            {"obs_collection": "JWST", "instrument_name": "NIRCam", "filters": "F090W", "s_ra": "1", "s_dec": "2", "t_exptime": "100"},
        ]
        workflow.target_var = type("Var", (), {"get": lambda self: "M51"})()
        rows = workflow.observatory_sensor_readiness_rows()
        self.assertEqual(rows[0]["sensor"], "WFC3 UVIS")
        self.assertEqual(rows[0]["readiness_status"], "ready")
        self.assertEqual(workflow.observatory_best_sensor_name(), "WFC3 UVIS")
        self.assertIn("Sensor Readiness Ranking", workflow.observatory_sensor_readiness_text())


    def test_cross_sensor_rgb_plan_combines_channels_from_multiple_sensors(self):
        workflow = SensorWorkflowHarness()
        workflow.product_results = [
            {"obs_collection": "HST", "instrument_name": "WFC3/UVIS", "Detector": "WFC3/UVIS", "filters": "F438W", "Spectral_Elt": "F438W", "productFilename": "hubble_blue.fits", "Format": "image/fits"},
            {"obs_collection": "HST", "instrument_name": "ACS/WFC", "Detector": "ACS/WFC", "filters": "F555W", "Spectral_Elt": "F555W", "productFilename": "acs_green.fits", "Format": "image/fits"},
            {"obs_collection": "JWST", "instrument_name": "NIRCam", "Detector": "NIRCam", "filters": "F444W", "Spectral_Elt": "F444W", "productFilename": "jwst_red.fits", "Format": "image/fits"},
        ]
        workflow.target_var = type("Var", (), {"get": lambda self: "M16"})()
        rgb_set = workflow.observatory_best_cross_sensor_rgb_set()
        self.assertIsNotNone(rgb_set)
        sensors = {workflow.observatory_sensor_family(rgb_set[channel]) for channel in ("blue", "green", "red")}
        self.assertGreater(len(sensors), 1)
        plan = workflow.observatory_cross_sensor_rgb_plan_text()
        self.assertIn("Recommended cross-sensor RGB set", plan)
        self.assertIn("Mixed sensors", plan)
        self.assertIn("Alignment note", plan)



if __name__ == "__main__":
    unittest.main()
