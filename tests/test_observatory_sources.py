import unittest

from hubble_workbench_app.observatory_sources import (
    layer_readiness_line,
    project_plan_lines,
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

    def test_layer_readiness_names_next_step(self):
        summary = {
            "by_mission": {"HST": 3},
            "products_by_mission": {"HST": 4},
            "channels_by_mission": {"HST": {"blue": 1, "green": 1, "red": 0}},
        }
        line = layer_readiness_line(summary, {"name": "Hubble", "code": "HST"})
        self.assertIn("products=4", line)
        self.assertIn("RGB blue=1, green=1, red=0", line)
        self.assertIn("missing red coverage", line)

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
        self.assertIn("Hubble (HST)", report)
        self.assertIn("current observations loaded: 3", report)
        self.assertIn("Planned context layers:", report)
        self.assertIn("Chandra (CHANDRA)", report)
        self.assertIn("[planned]", report)


if __name__ == "__main__":
    unittest.main()