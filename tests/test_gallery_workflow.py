import tempfile
import unittest
from pathlib import Path

from PIL import Image

from hubble_workbench_app.gallery_workflow import GalleryWorkflowMixin


class GalleryWorkflowTests(unittest.TestCase):
    def test_discovers_images_and_creates_reusable_thumbnail_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = root / "outputs"
            notes = root / "notes"
            cache = outputs / ".gallery_cache"
            outputs.mkdir()
            notes.mkdir()
            image_path = outputs / "m42_rgb_20260728_120000.png"
            Image.new("RGB", (640, 320), (10, 20, 30)).save(image_path)
            (notes / "m42_rgb_20260728_120000_notes.txt").write_text(
                "M42 color composite\nCreated: today\n",
                encoding="utf-8",
            )

            first = GalleryWorkflowMixin.discover_gallery_images(outputs, notes, cache)
            second = GalleryWorkflowMixin.discover_gallery_images(outputs, notes, cache)

            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["description"], "M42 color composite")
            self.assertEqual((first[0]["width"], first[0]["height"]), (640, 320))
            self.assertTrue(first[0]["thumbnail_path"].is_file())
            self.assertEqual(first[0]["thumbnail_path"], second[0]["thumbnail_path"])

    def test_gallery_filters_by_query_type_and_sort(self):
        items = [
            {"name": "m42.png", "description": "Orion Nebula", "kind": "PNG", "modified": 20},
            {"name": "m51.tif", "description": "Whirlpool Galaxy", "kind": "TIFF", "modified": 10},
        ]
        self.assertEqual(
            [item["name"] for item in GalleryWorkflowMixin.filter_gallery_items(items, "galaxy")],
            ["m51.tif"],
        )
        self.assertEqual(
            [item["name"] for item in GalleryWorkflowMixin.filter_gallery_items(items, kind="TIFF")],
            ["m51.tif"],
        )
        self.assertEqual(
            [item["name"] for item in GalleryWorkflowMixin.filter_gallery_items(items, sort_order="Oldest")],
            ["m51.tif", "m42.png"],
        )

    def test_fast_discovery_can_defer_thumbnail_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = root / "outputs"
            cache = outputs / ".gallery_cache"
            outputs.mkdir()
            image_path = outputs / "deferred.tif"
            Image.new("RGB", (100, 50), (1, 2, 3)).save(image_path)

            items = GalleryWorkflowMixin.discover_gallery_images(
                outputs,
                root / "notes",
                cache,
                generate_thumbnails=False,
            )

            self.assertEqual(len(items), 1)
            self.assertIsNone(items[0]["thumbnail_path"])
            GalleryWorkflowMixin.ensure_gallery_thumbnail(items[0], cache)
            self.assertTrue(items[0]["thumbnail_path"].is_file())

    def test_gallery_details_include_dimensions_and_description(self):
        text = GalleryWorkflowMixin.gallery_item_details({
            "name": "m42.png",
            "description": "Orion Nebula composite.",
            "kind": "PNG",
            "width": 1200,
            "height": 800,
            "size": 1024 * 1024,
            "modified": 0,
            "path": Path("m42.png"),
        })
        self.assertIn("Orion Nebula", text)
        self.assertIn("1,200 x 800", text)
        self.assertIn("1.00 MB", text)


if __name__ == "__main__":
    unittest.main()
