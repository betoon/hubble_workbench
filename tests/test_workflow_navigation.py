import unittest

from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin
from hubble_workbench_app.debug_console import DEBUG_SHOW_ON_ISSUE_DEFAULT
from hubble_workbench_app.app_utilities import responsive_toolbar_positions, responsive_window_layout


class _Value:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _Notebook:
    def __init__(self):
        self.selected = None

    def select(self, tab):
        self.selected = tab


class WorkflowNavigationTests(unittest.TestCase):
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
