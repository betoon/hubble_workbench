import tempfile
import unittest
from pathlib import Path
from hubble_workbench_app.observatory_sources import project_state, project_plan_lines

class WizardProjectTests(unittest.TestCase):
    def test_existing_mast_readiness_is_unchanged(self):
        summary = {"by_mission": {"HST": 2}, "products_by_mission": {"HST": 3}}
        before = project_state(summary)
        after = project_state(summary, [{"source": "WISE", "key": "w", "band": "W1"}])
        self.assertEqual(before["active_sources"], after["active_sources"])
        self.assertEqual(before["active_ready_for_rgb"], after["active_ready_for_rgb"])

    def test_files_assignments_targets_and_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "image.fits"
            path.write_bytes(b"test")
            one = dict(source="Pan-STARRS", key="one", band="g", target="M51", local_path=str(path))
            two = dict(source="Pan-STARRS", key="two", band="r", target="M51", local_path=str(path.parent / "missing.fits"))
            rows = [one, one, two]
            state = project_state({}, rows, {"red": two, "blue": one})
            ps = next(s for s in state["wizard_sources"] if s["code"] == "PANSTARRS")
            self.assertEqual((ps["records"], ps["downloaded"], ps["missing_files"]), (2, 1, 1))
            self.assertEqual(ps["assigned_channels"], ["red", "blue"])
            report = "\n".join(project_plan_lines({}, rows, {"blue": one}))
            self.assertIn("Targets: M51", report)
            self.assertIn("Fewer than three distinct bands", report)
            self.assertIn("Re-download missing files", report)

    def test_legacy_project_without_wizard_state(self):
        state = project_state()
        self.assertEqual(len(state["wizard_sources"]), 8)
        self.assertTrue(all(s["records"] == 0 for s in state["wizard_sources"]))
        self.assertEqual(len(state["active_sources"]), 2)

if __name__ == "__main__":
    unittest.main()
