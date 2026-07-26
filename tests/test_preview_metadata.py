import unittest

import numpy as np

from hubble_workbench_app.preview_workflow import PreviewWorkflowMixin


class PreviewMetadataTests(unittest.TestCase):
    def test_image_statistics_ignore_nonfinite_values(self):
        stats = PreviewWorkflowMixin.preview_image_statistics(np.array([[1.0, 2.0], [np.nan, 5.0]]))
        self.assertEqual(stats["finite"], 3)
        self.assertEqual(stats["minimum"], 1.0)
        self.assertEqual(stats["maximum"], 5.0)

    def test_metadata_summary_includes_observation_wcs_and_field_size(self):
        header = {
            "TARGNAME": "M42",
            "TELESCOP": "JWST",
            "INSTRUME": "NIRCAM",
            "CRVAL1": 83.8,
            "CRVAL2": -5.4,
            "CDELT1": -0.00001,
            "CDELT2": 0.00001,
        }
        summary = PreviewWorkflowMixin.preview_metadata_summary(header, (100, 200), path="example.fits")
        self.assertIn("M42", summary)
        self.assertIn("JWST", summary)
        self.assertIn("Pixel scale", summary)
        self.assertIn("field of view", summary)

    def test_header_search_matches_keys_and_values(self):
        header = {"TELESCOP": "JWST", "INSTRUME": "NIRCAM", "FILTER": "F150W2"}
        self.assertIn("INSTRUME", PreviewWorkflowMixin.preview_header_text(header, "nircam"))
        self.assertNotIn("TELESCOP", PreviewWorkflowMixin.preview_header_text(header, "nircam"))
        self.assertIn("FILTER", PreviewWorkflowMixin.preview_header_text(header, "filter"))


if __name__ == "__main__":
    unittest.main()
