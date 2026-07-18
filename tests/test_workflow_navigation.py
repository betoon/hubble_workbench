import unittest

from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin
from hubble_workbench_app.debug_console import DEBUG_SHOW_ON_ISSUE_DEFAULT


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
