import unittest
import xml.etree.ElementTree as ET
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from hubble_workbench_app.preview_workflow import PreviewWorkflowMixin
from hubble_workbench_app.image_processing import normalize_image, normalize_image_uint16


class PreviewMetadataTests(unittest.TestCase):
    def test_preview_canvas_ignores_photo_placeholder_before_render(self):
        workflow = SimpleNamespace(preview_photo=None, preview_image=None)
        self.assertIsNone(
            PreviewWorkflowMixin.preview_canvas_display_point(workflow, 10, 10)
        )
        self.assertIsNone(
            PreviewWorkflowMixin.preview_canvas_motion(
                workflow, SimpleNamespace(x=10, y=10)
            )
        )

    def test_linear_preview_stretch_does_not_apply_asinh(self):
        data = np.array([[0.0, 0.5, 1.0]])
        linear = normalize_image(data, low_percent=0, high_percent=100, stretch="linear")
        asinh = normalize_image(data, low_percent=0, high_percent=100, stretch="asinh")
        self.assertEqual(int(linear[0, 1]), 127)
        self.assertNotEqual(int(linear[0, 1]), int(asinh[0, 1]))

    def test_uint16_preview_normalization_preserves_more_levels(self):
        data = np.linspace(0, 1, 1024).reshape(1, -1)
        eight_bit = normalize_image(data, low_percent=0, high_percent=100, stretch="linear")
        sixteen_bit = normalize_image_uint16(data, low_percent=0, high_percent=100, stretch="linear")
        self.assertEqual(sixteen_bit.dtype, np.uint16)
        self.assertGreater(len(np.unique(sixteen_bit)), len(np.unique(eight_bit)))
        self.assertEqual(int(sixteen_bit[0, -1]), 65535)

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

    def test_header_cards_show_type_and_comment(self):
        cards = [{"keyword": "TELESCOP", "value": "JWST", "type": "str", "comment": "Observatory name"}]
        text = PreviewWorkflowMixin.preview_header_text({}, cards=cards)
        self.assertIn("[str]", text)
        self.assertIn("Observatory name", text)

    def test_hdu_inventory_marks_preview_extension(self):
        text = PreviewWorkflowMixin.preview_hdu_inventory_text([
            {"index": 0, "name": "PRIMARY", "type": "PrimaryHDU", "shape": (), "bitpix": 8, "cards": 5, "selected": False},
            {"index": 1, "name": "SCI", "type": "ImageHDU", "shape": (20, 30), "bitpix": -32, "cards": 12, "selected": True},
        ])
        self.assertIn("*1", text)
        self.assertIn("30 x 20", text)
        self.assertIn("Total extensions: 2", text)

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

    def test_vertical_flip_maps_display_row_back_to_source_row(self):
        self.assertEqual(
            PreviewWorkflowMixin.preview_display_to_source_point((12, 3), (100, 50), False),
            (12, 3),
        )
        self.assertEqual(
            PreviewWorkflowMixin.preview_display_to_source_point((12, 3), (100, 50), True),
            (12, 46),
        )

    def test_frozen_probe_text_includes_capture_and_readout(self):
        text = PreviewWorkflowMixin.preview_frozen_probe_text(
            "Pixel X 12, Y 34\nRA 10.0 degrees",
            "2026-07-26 12:00:00",
        )
        self.assertIn("FROZEN PIXEL PROBE", text)
        self.assertIn("2026-07-26 12:00:00", text)
        self.assertIn("Pixel X 12, Y 34", text)

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

    def test_histogram_uses_selected_stretch_percentiles(self):
        histogram = PreviewWorkflowMixin.preview_histogram(
            np.arange(1001, dtype=float),
            black_percent=10,
            white_percent=90,
        )
        self.assertAlmostEqual(histogram["black"], 100.0)
        self.assertAlmostEqual(histogram["white"], 900.0)

    def test_stretch_percentiles_validate_order_and_range(self):
        self.assertEqual(PreviewWorkflowMixin.preview_stretch_percentiles("0.5", "99.5"), (0.5, 99.5))
        with self.assertRaises(ValueError):
            PreviewWorkflowMixin.preview_stretch_percentiles(90, 10)
        with self.assertRaises(ValueError):
            PreviewWorkflowMixin.preview_stretch_percentiles(-1, 99)

    def test_stretch_settings_payload_normalizes_persisted_values(self):
        payload = PreviewWorkflowMixin.preview_stretch_settings_payload(
            "ASINH",
            "0.25",
            "99.75",
            crosshair=1,
            flip_vertical=0,
        )
        self.assertEqual(payload["fits_preview_stretch"], "asinh")
        self.assertEqual(payload["fits_preview_black_percent"], 0.25)
        self.assertEqual(payload["fits_preview_white_percent"], 99.75)
        self.assertTrue(payload["fits_preview_crosshair"])
        self.assertFalse(payload["fits_preview_flip_vertical"])
        self.assertEqual(payload["fits_preview_export_bit_depth"], 8)

    def test_histogram_x_clamps_values_to_plot(self):
        position = PreviewWorkflowMixin.preview_histogram_x(5, 0, 10, 40, 240)
        self.assertEqual(position, 140)
        self.assertEqual(PreviewWorkflowMixin.preview_histogram_x(-5, 0, 10, 40, 240), 40)
        self.assertEqual(PreviewWorkflowMixin.preview_histogram_x(15, 0, 10, 40, 240), 240)

    def test_hdu_choices_include_images_and_count_cube_planes(self):
        choices = PreviewWorkflowMixin.preview_image_hdu_choices([
            {"index": 0, "name": "PRIMARY", "shape": ()},
            {"index": 1, "name": "SCI", "shape": (20, 30)},
            {"index": 2, "name": "ERR", "shape": (4, 20, 30)},
            {"index": 3, "name": "DQ", "shape": (2, 3, 20, 30)},
        ])
        self.assertEqual([item[1] for item in choices], [1, 2, 3])
        self.assertEqual([item[2] for item in choices], [1, 4, 6])

    def test_avm_metadata_prefills_from_fits_header(self):
        metadata = PreviewWorkflowMixin.avm_metadata_from_header({
            "OBJECT": "M42",
            "TELESCOP": "JWST",
            "INSTRUME": "NIRCAM",
            "FILTER": "F200W",
            "ORIGIN": "STScI",
        })
        self.assertEqual(metadata["title"], "M42")
        self.assertEqual(metadata["facility"], "JWST")
        self.assertEqual(metadata["instrument"], "NIRCAM")
        self.assertEqual(metadata["spectral_band"], "F200W")

    def test_avm_metadata_prefills_wcs_observation_and_dimensions(self):
        metadata = PreviewWorkflowMixin.avm_metadata_from_header({
            "CRVAL1": 83.633,
            "CRVAL2": -5.391,
            "CDELT1": -0.00001,
            "CDELT2": 0.00001,
            "RADESYS": "ICRS",
            "NAXIS1": 2048,
            "NAXIS2": 1024,
            "DATE-OBS": "2025-01-02",
            "EXPTIME": 1200.5,
            "PROPOSID": "12345",
        })
        self.assertEqual(metadata["ra"], "83.633")
        self.assertEqual(metadata["dec"], "-5.391")
        self.assertEqual(metadata["scale_x"], "1e-05")
        self.assertEqual(metadata["reference_frame"], "ICRS")
        self.assertEqual(metadata["image_width"], "2048")
        self.assertEqual(metadata["exposure_time"], "1200.5")
        self.assertEqual(metadata["proposal_id"], "12345")

    def test_avm_completeness_reports_missing_fields_and_wcs(self):
        metadata = {field: "complete" for field in PreviewWorkflowMixin.AVM_COMPLETENESS_FIELDS}
        metadata.update({"ra": "1", "dec": "2", "scale_x": "0.1", "scale_y": "0.1"})
        complete = PreviewWorkflowMixin.avm_completeness(metadata)
        self.assertEqual(complete["percent"], 100)
        self.assertTrue(complete["wcs_complete"])
        metadata["rights"] = ""
        incomplete = PreviewWorkflowMixin.avm_completeness(metadata)
        self.assertIn("rights", incomplete["missing"])
        self.assertLess(incomplete["percent"], 100)

    def test_avm_creator_template_only_contains_reusable_identity_fields(self):
        template = PreviewWorkflowMixin.avm_creator_template({
            "creator": "Brian",
            "rights": "CC BY 4.0",
            "title": "M42",
        })
        self.assertEqual(template["creator"], "Brian")
        self.assertEqual(template["rights"], "CC BY 4.0")
        self.assertNotIn("title", template)

    def test_avm_xmp_packet_is_valid_xml_and_escapes_metadata(self):
        packet = PreviewWorkflowMixin.avm_xmp_packet({
            "title": "M42 & Friends",
            "creator": 'A "Researcher"',
            "facility": "JWST",
        })
        xml_text = packet[packet.index("<x:xmpmeta"):packet.index("<?xpacket end")]
        root = ET.fromstring(xml_text)
        self.assertTrue(root.tag.endswith("xmpmeta"))
        self.assertIn("M42 &amp; Friends", packet)
        self.assertIn("JWST", packet)
        self.assertIn("Spatial.ReferenceValue", packet)

    def test_avm_metadata_is_embedded_in_png_and_tiff_exports(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png_path = root / "example.png"
            tif_path = root / "example.tif"
            metadata = {"title": "M42", "creator": "Workbench"}
            image = Image.new("L", (8, 8), 127)
            PreviewWorkflowMixin.save_image_with_avm(image, png_path, metadata)
            PreviewWorkflowMixin.save_image_with_avm(image, tif_path, metadata)
            with Image.open(png_path) as png:
                self.assertIn("M42", png.info.get("XML:com.adobe.xmp", ""))
            with Image.open(tif_path) as tif:
                embedded = tif.tag_v2.get(700, b"")
                if isinstance(embedded, bytes):
                    embedded = embedded.decode("utf-8", "replace")
                self.assertIn("Workbench", embedded)


if __name__ == "__main__":
    unittest.main()
