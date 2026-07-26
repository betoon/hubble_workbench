import tempfile
import unittest
from pathlib import Path

from hubble_workbench_app.preview_workflow import PreviewWorkflowMixin


class RecentFitsFilesTests(unittest.TestCase):
    def test_discovers_nested_fits_files_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "M17" / "run"
            nested.mkdir(parents=True)
            older = nested / "older.fits"
            newer = nested / "newer.fits.gz"
            ignored = nested / "preview.png"
            older.write_bytes(b"fits")
            newer.write_bytes(b"fits")
            ignored.write_bytes(b"png")
            older.touch()
            newer.touch()

            files = PreviewWorkflowMixin.discover_recent_fits_files(root)

            self.assertEqual(set(files), {older, newer})
            self.assertNotIn(ignored, files)

    def test_recent_fits_limit_is_respected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(5):
                (root / f"{index}.fits").write_bytes(b"fits")
            self.assertEqual(len(PreviewWorkflowMixin.discover_recent_fits_files(root, limit=2)), 2)


if __name__ == "__main__":
    unittest.main()
