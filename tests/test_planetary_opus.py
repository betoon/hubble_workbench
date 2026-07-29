import unittest
from urllib.parse import parse_qs, urlparse

from hubble_workbench_app.planetary_opus import (
    build_opus_search_url,
    opus_product_page_url,
    parse_opus_product_files,
    parse_opus_search_results,
)


class PlanetaryOpusTests(unittest.TestCase):
    def test_search_url_contains_planet_instrument_columns_and_limit(self):
        url = build_opus_search_url(
            {"planet": "Saturn", "instrument": "Cassini ISS"},
            limit=500,
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["planet"], ["Saturn"])
        self.assertEqual(query["instrument"], ["Cassini ISS"])
        self.assertEqual(query["limit"], ["100"])
        self.assertIn("opusid", query["cols"][0])

    def test_search_results_join_metadata_and_preview_by_opus_id(self):
        metadata = {
            "page": [[
                "co-iss-w123",
                "Cassini ISS",
                "Saturn",
                "Saturn",
                "2004-01-01T00:00:00",
                "12.5",
            ]]
        }
        images = {
            "data": [{
                "opus_id": "co-iss-w123",
                "url": "https://opus.example/preview.jpg",
            }]
        }
        product = parse_opus_search_results(metadata, images)[0]
        self.assertEqual(product["Observation_id"], "co-iss-w123")
        self.assertEqual(product["_OPUS_preview_url"], "https://opus.example/preview.jpg")
        self.assertIn("view=detail", product["ProductURL"])

    def test_product_page_uses_official_short_detail_url(self):
        self.assertEqual(
            opus_product_page_url("co-iss-w123"),
            "https://opus.pds-rings.seti.org/opus/#/view=detail&detail=co-iss-w123",
        )

    def test_file_parser_flattens_product_types_and_removes_duplicates(self):
        payload = {
            "data": {
                "co-iss-w123": {
                    "coiss_raw": [
                        "https://opus.example/raw.img",
                        "https://opus.example/raw.lbl",
                    ],
                    "coiss_calib": [
                        "https://opus.example/calib.img",
                        "https://opus.example/raw.lbl",
                    ],
                }
            }
        }
        files = parse_opus_product_files(payload, "co-iss-w123")
        self.assertEqual(len(files), 3)
        self.assertEqual(files[0]["FileName"], "raw.img")


if __name__ == "__main__":
    unittest.main()
