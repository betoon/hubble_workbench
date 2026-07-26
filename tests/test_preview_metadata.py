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

    def test_canvas_point_maps_centered_scaled_preview_to_full_image(self):
        point = PreviewWorkflowMixin.preview_canvas_to_image_point(
            500,
            300,
            canvas_size=(1000, 600),
            rendered_size=(800, 400),
            image_size=(4000, 2000),
        )
        self.assertEqual(point, (2000, 1000))
        self.assertIsNone(PreviewWorkflowMixin.preview_canvas_to_image_point(
            50,
            50,
            canvas_size=(1000, 600),
            rendered_size=(800, 400),
            image_size=(4000, 2000),
        ))

    def test_sky_position_formats_degrees_and_sexagesimal(self):
        text = PreviewWorkflowMixin.preview_format_sky_position(83.633, -5.391)
        self.assertIn("83.633000", text)
        self.assertIn("05h", text)
        self.assertIn("-05°", text)

    def test_histogram_tracks_black_and_white_percentiles(self):
        histogram = PreviewWorkflowMixin.preview_histogram(np.arange(1000, dtype=float), bins=50)
        self.assertEqual(len(histogram["counts"]), 50)
        self.assertEqual(len(histogram["edges"]), 51)
        self.assertLess(histogram["black"], histogram["white"])
        self.assertEqual(histogram["sampled"], 1000)

    def test_histogram_x_clamps_values_to_plot(self):
        position = PreviewWorkflowMixin.preview_histogram_x(5, 0, 10, 40, 240)
        self.assertEqual(position, 140)
        self.assertEqual(PreviewWorkflowMixin.preview_histogram_x(-5, 0, 10, 40, 240), 40)
        self.assertEqual(PreviewWorkflowMixin.preview_histogram_x(15, 0, 10, 40, 240), 240)


if __name__ == "__main__":
    unittest.main()
