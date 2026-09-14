import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from tests.test_rgb_selection import Picker, row
from hubble_workbench_app.browser_activity import BrowserActivityMixin


class FeedbackTests(unittest.TestCase):
    def test_label_reports_filters_coverage_and_total_size(self):
        picks = {ch: row(ch) for ch in ("blue", "green", "red")}
        for item in picks.values():
            item["size"] = 500000000
        label = Picker().suggested_rgb_label(picks)
        for text in ("F435W", "F555W", "F814W", "ACS/WFC", "estimated overlap", "1.50 GB"):
            self.assertIn(text, label)

    def test_unknown_metadata_is_labeled_honestly(self):
        picks = {ch: row(ch) for ch in ("blue", "green", "red")}
        picks["blue"].pop("s_ra")
        label = Picker().suggested_rgb_label(picks)
        self.assertIn("coverage unverified", label)
        self.assertIn("size unknown", label)

    def test_best_available_does_not_pick_incompatible_sensors(self):
        picker = Picker()
        picker.rgb_candidate_rows = {ch: [row(ch)] for ch in ("blue", "green", "red")}
        picker.rgb_candidate_rows["blue"][0]["instrument_name"] = "WFC3/UVIS"
        picker.select_rgb_candidate_row = Mock()
        picker.browser_status = Mock()
        picker.pick_best_available_rgb_channels()
        picker.select_rgb_candidate_row.assert_not_called()
        self.assertIn("No compatible RGB set", picker.browser_status.set.call_args.args[0])

    def test_stage_updates_ignore_stale_operations(self):
        harness = SimpleNamespace(browser_operation_id=2, browser_busy_message="Searching",
                                  extend_browser_timeout=Mock(), download_progress_var=Mock(),
                                  download_detail=Mock(), log_background_activity=Mock())
        BrowserActivityMixin.set_download_progress(harness, 2, 45, "Downloading selected channels")
        self.assertEqual(harness.browser_busy_message, "Downloading selected channels")
        BrowserActivityMixin.set_download_progress(harness, 1, 80, "Old operation")
        self.assertEqual(harness.browser_busy_message, "Downloading selected channels")


if __name__ == "__main__":
    unittest.main()
