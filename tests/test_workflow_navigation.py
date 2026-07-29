import unittest
import tempfile
from pathlib import Path

import numpy as np

from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin
from hubble_workbench_app.debug_console import DEBUG_SHOW_ON_ISSUE_DEFAULT
from hubble_workbench_app.app_utilities import (
    responsive_content_height,
    mousewheel_scroll_units,
    responsive_pane_orientation,
    responsive_tab_titles,
    responsive_toolbar_positions,
    responsive_window_layout,
)


class _Value:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _Notebook:
    def __init__(self):
        self.selected = None

    def select(self, tab):
        self.selected = tab


class WorkflowNavigationTests(unittest.TestCase):
    def test_color_composer_accepts_two_channels_and_reports_missing_color(self):
        available, missing = ComposeWorkflowMixin.compose_channel_plan([
            "red.fits",
            "",
            "blue.fits",
        ])
        self.assertEqual(available, [("red", "red.fits"), ("blue", "blue.fits")])
        self.assertEqual(missing, ["green"])

    def test_color_composer_rejects_only_one_channel(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            ComposeWorkflowMixin.compose_channel_plan(["red.fits", "", ""])

    def test_color_composer_zero_fills_missing_plane(self):
        red = np.full((2, 3), 10, dtype=np.uint8)
        blue = np.full((2, 3), 30, dtype=np.uint8)
        (output_red, output_green, output_blue), method = (
            ComposeWorkflowMixin.complete_rgb_channels(
                {"red": red, "blue": blue},
                "Zero fill",
            )
        )
        np.testing.assert_array_equal(output_red, red)
        np.testing.assert_array_equal(output_green, np.zeros_like(red))
        np.testing.assert_array_equal(output_blue, blue)
        self.assertIn("zero-filled green", method)

    def test_color_composer_can_average_synthesize_missing_plane(self):
        red = np.full((2, 3), 10, dtype=np.uint8)
        blue = np.full((2, 3), 30, dtype=np.uint8)
        (_output_red, output_green, _output_blue), method = (
            ComposeWorkflowMixin.complete_rgb_channels(
                {"red": red, "blue": blue},
                "Average available",
            )
        )
        np.testing.assert_array_equal(output_green, np.full((2, 3), 20, dtype=np.uint8))
        self.assertIn("average-synthesized green", method)

    def test_composer_channel_preview_opens_fits_preview_tab(self):
        class Notebook:
            def __init__(self):
                self.selected = None

            def select(self, tab):
                self.selected = tab

        class Harness(ComposeWorkflowMixin):
            def __init__(self):
                self.compose_status = _Value()
                self.convert_path_var = _Value()
                self.convert_tab = object()
                self.notebook = Notebook()
                self.preview_calls = 0

            def preview_fits_async(self):
                self.preview_calls += 1

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "single_channel.fits"
            path.touch()
            harness = Harness()
            result = harness.preview_compose_channel(_Value(str(path)), "red")

        self.assertTrue(result)
        self.assertEqual(harness.convert_path_var.value, str(path))
        self.assertIs(harness.notebook.selected, harness.convert_tab)
        self.assertEqual(harness.preview_calls, 1)

    def test_clear_composer_channel_allows_intentional_omission(self):
        class Harness(ComposeWorkflowMixin):
            def __init__(self):
                self.compose_status = _Value()

        variable = _Value("green.fits")
        Harness().clear_compose_channel(variable, "green")
        self.assertEqual(variable.value, "")

    def test_responsive_window_layout_fits_small_monitor(self):
        layout = responsive_window_layout(800, 600)
        self.assertLessEqual(layout["width"] + layout["x"], 800)
        self.assertLessEqual(layout["height"] + layout["y"], 600)
        self.assertLessEqual(layout["minimum_width"], layout["width"])
        self.assertLessEqual(layout["minimum_height"], layout["height"])

    def test_responsive_window_layout_keeps_preferred_desktop_size(self):
        layout = responsive_window_layout(1920, 1080)
        self.assertEqual((layout["width"], layout["height"]), (1160, 760))
        self.assertEqual((layout["minimum_width"], layout["minimum_height"]), (940, 620))

    def test_responsive_toolbar_positions_wrap_crowded_rows(self):
        positions = responsive_toolbar_positions(300, [100, 100, 100, 80], gap=6)
        self.assertEqual(positions, [(0, 0), (0, 1), (1, 0), (1, 1)])

    def test_responsive_toolbar_positions_stay_single_row_when_wide(self):
        positions = responsive_toolbar_positions(600, [100, 100, 100, 80], gap=6)
        self.assertEqual(positions, [(0, 0), (0, 1), (0, 2), (0, 3)])

    def test_responsive_tab_titles_compact_on_narrow_window(self):
        self.assertEqual(
            responsive_tab_titles(900),
            ("Setup", "MAST", "Explorer", "Planets", "FITS", "Composer", "H-II", "Gallery", "Debug"),
        )
        self.assertEqual(responsive_tab_titles(1200)[1], "MAST Browser")

    def test_responsive_content_height_is_bounded(self):
        self.assertEqual(responsive_content_height(600), 340)
        self.assertEqual(responsive_content_height(400), 280)
        self.assertEqual(responsive_content_height(1000), 520)

    def test_responsive_pane_orientation_stacks_narrow_views(self):
        self.assertEqual(responsive_pane_orientation(900), "vertical")
        self.assertEqual(responsive_pane_orientation(1200), "horizontal")

    def test_mousewheel_scroll_units_supports_standard_and_small_deltas(self):
        self.assertEqual(mousewheel_scroll_units(120), -1)
        self.assertEqual(mousewheel_scroll_units(-240), 2)
        self.assertEqual(mousewheel_scroll_units(30), -1)
        self.assertEqual(mousewheel_scroll_units(0), 0)

    def test_debug_console_auto_focus_is_opt_in(self):
        self.assertFalse(DEBUG_SHOW_ON_ISSUE_DEFAULT)

    def test_successful_compose_finishes_on_color_composer(self):
        class Harness(ComposeWorkflowMixin):
            def __init__(self):
                self.notebook = _Notebook()
                self.compose_tab = object()
                self.compose_status = _Value()

            def generate_preset_previews(self):
                pass

            def auto_save_preview_png(self):
                return None

        harness = Harness()
        harness.finish_compose_extras("640 x 480", "")

        self.assertIs(harness.notebook.selected, harness.compose_tab)
        self.assertIn("RGB composite ready", harness.compose_status.value)


if __name__ == "__main__":
    unittest.main()
