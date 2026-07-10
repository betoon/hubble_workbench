import unittest

from hubble_workbench_app.observatory_sources import (
    layer_readiness_line,
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


if __name__ == "__main__":
    unittest.main()