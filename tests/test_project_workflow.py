import tempfile
import time
import unittest
from pathlib import Path

from hubble_workbench_app.project_workflow import ProjectWorkflowMixin


class ProjectWorkflowTests(unittest.TestCase):
    def test_composite_channel_metadata_preserves_filter_color_assignments(self):
        channels = ProjectWorkflowMixin.composite_channel_metadata([
            {"TELESCOP": "HST", "INSTRUME": "WFC3", "FILTER": "F814W"},
            {"TELESCOP": "HST", "INSTRUME": "WFC3", "FILTER": "F555W"},
            {"TELESCOP": "JWST", "INSTRUME": "NIRCAM", "FILTER": "F200W"},
        ])
        self.assertEqual([item["color"] for item in channels], ["Red", "Green", "Blue"])
        self.assertEqual(channels[0]["filters"], ["F814W"])
        self.assertEqual(channels[2]["facility"], "JWST")

    def test_safe_project_name_handles_target_names_and_empty_values(self):
        self.assertEqual(ProjectWorkflowMixin.safe_project_name("M 42 / Orion"), "M_42_Orion")
        self.assertEqual(ProjectWorkflowMixin.safe_project_name(""), "untitled")

    def test_recent_projects_are_newest_first_and_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older = root / "older.json"
            newer = root / "newer.json"
            ignored = root / "notes.txt"
            older.write_text("{}", encoding="utf-8")
            time.sleep(0.02)
            newer.write_text("{}", encoding="utf-8")
            ignored.write_text("ignore", encoding="utf-8")

            projects = ProjectWorkflowMixin.discover_recent_projects(root)
            self.assertEqual(projects, [newer, older])
            self.assertEqual(
                ProjectWorkflowMixin.discover_recent_projects(root, limit=1),
                [newer],
            )


if __name__ == "__main__":
    unittest.main()
