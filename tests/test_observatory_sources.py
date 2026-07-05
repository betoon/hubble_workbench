import unittest

from hubble_workbench_app.observatory_sources import project_plan_lines, source_observation_count


class ObservatorySourceTests(unittest.TestCase):
    def test_source_observation_count_matches_known_codes(self):
        summary = {"by_mission": {"HST": 3, "JWST": 2, "Other": 1}}
        self.assertEqual(source_observation_count(summary, {"name": "Hubble", "code": "HST"}), 3)
        self.assertEqual(source_observation_count(summary, {"name": "James Webb", "code": "JWST"}), 2)

    def test_project_plan_marks_loaded_and_planned_sources(self):
        summary = {"observations": 3, "by_mission": {"HST": 3}}
        lines = project_plan_lines(summary)
        report = "\n".join(lines)
        self.assertIn("Active search sources:", report)
        self.assertIn("Hubble (HST)", report)
        self.assertIn("current observations loaded: 3", report)
        self.assertIn("Planned context layers:", report)
        self.assertIn("Chandra (CHANDRA)", report)
        self.assertIn("[planned]", report)


if __name__ == "__main__":
    unittest.main()