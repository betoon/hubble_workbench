import sys
import unittest

from hubble_workbench_app.dependency_status import DependencyStatusMixin


class DependencyStatusTests(unittest.TestCase):
    def test_interpreter_detail_identifies_running_python(self):
        detail = DependencyStatusMixin.dependency_interpreter_detail()
        self.assertIn("Python interpreter:", detail)
        self.assertIn(sys.executable, detail)


if __name__ == "__main__":
    unittest.main()
