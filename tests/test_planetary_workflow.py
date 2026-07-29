import unittest
from urllib.parse import parse_qs, urlparse

from hubble_workbench_app.planetary_workflow import PlanetaryWorkflowMixin


class PlanetaryWorkflowTests(unittest.TestCase):
    def test_mars_search_bounds_normalize_longitude_and_clamp_latitude(self):
        bounds = PlanetaryWorkflowMixin.mars_search_bounds(89.9, -133.8, 1.0)
        self.assertEqual(bounds["maxlat"], 90.0)
        self.assertAlmostEqual(bounds["westernlon"], 225.2)
        self.assertAlmostEqual(bounds["easternlon"], 227.2)

    def test_ode_url_uses_valid_hirise_codes_and_bounded_limit(self):
        dataset = "MRO HiRISE — projected color/red"
        url = PlanetaryWorkflowMixin.build_mars_ode_url(18.38, 77.58, 0.25, dataset, limit=500)
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["ihid"], ["MRO"])
        self.assertEqual(query["iid"], ["HiRISE"])
        self.assertEqual(query["pt"], ["RDRV11"])
        self.assertEqual(query["limit"], ["100"])
        self.assertEqual(query["output"], ["json"])

    def test_ode_response_accepts_single_product_or_list(self):
        single = {
            "ODEResults": {
                "Status": "Success",
                "Products": {"Product": {"Observation_id": "ONE"}},
            }
        }
        multiple = {
            "ODEResults": {
                "Status": "Success",
                "Products": {"Product": [{"Observation_id": "ONE"}, {"Observation_id": "TWO"}]},
            }
        }
        self.assertEqual(len(PlanetaryWorkflowMixin.parse_mars_ode_response(single)), 1)
        self.assertEqual(len(PlanetaryWorkflowMixin.parse_mars_ode_response(multiple)), 2)

    def test_map_coordinate_round_trip(self):
        x, y = PlanetaryWorkflowMixin.planetary_map_point(18.38, 77.58, 800, 400)
        latitude, longitude = PlanetaryWorkflowMixin.planetary_map_coordinates(x, y, 800, 400)
        self.assertAlmostEqual(latitude, 18.38)
        self.assertAlmostEqual(longitude, 77.58)

    def test_planetary_product_details_include_science_geometry(self):
        text = PlanetaryWorkflowMixin.planetary_product_details({
            "Observation_id": "ESP_TEST",
            "Comment": "Jezero delta",
            "Center_latitude": "18.4",
            "Center_longitude": "77.6",
            "Map_scale": "0.25",
            "Incidence_angle": "45",
            "ProductURL": "https://example.invalid/product",
        }, "HiRISE")
        self.assertIn("ESP_TEST", text)
        self.assertIn("Jezero delta", text)
        self.assertIn("0.25 m/pixel", text)
        self.assertIn("Incidence angle", text)

    def test_product_id_falls_back_to_ode_product_url(self):
        product_id = PlanetaryWorkflowMixin.planetary_product_id({
            "ProductURL": "https://ode.example/product?product_id=P02_TEST&product_idGeo=1",
        })
        self.assertEqual(product_id, "P02_TEST")

    def test_preview_url_uses_ode_thumbnail_query_and_product_id(self):
        url = PlanetaryWorkflowMixin.build_mars_asset_url(
            {"Observation_id": "ESP_TEST"},
            "thumbnail",
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["target"], ["mars"])
        self.assertEqual(query["query"], ["thumbnail"])
        self.assertEqual(query["pdsid"], ["ESP_TEST"])

    def test_preview_url_prefers_specific_archive_product_id(self):
        url = PlanetaryWorkflowMixin.build_mars_asset_url({
            "Observation_id": "ESP_TEST",
            "ProductURL": "https://ode.example/product?product_id=ESP_TEST_COLOR",
        })
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["pdsid"], ["ESP_TEST_COLOR"])

    def test_preview_url_rejects_unknown_asset_type(self):
        with self.assertRaises(ValueError):
            PlanetaryWorkflowMixin.build_mars_asset_url(
                {"Observation_id": "ESP_TEST"},
                "unknown",
            )

    def test_planetary_footprint_points_parse_c0_polygon(self):
        points = PlanetaryWorkflowMixin.planetary_footprint_points({
            "Footprint_C0_geometry": "POLYGON ((77.3 17.6, 77.2 18.1, 77.3 17.6))",
        })
        self.assertEqual(points[0], (17.6, 77.3))
        self.assertEqual(len(points), 3)

    def test_planetary_footprint_points_ignore_empty_or_invalid_geometry(self):
        self.assertEqual(
            PlanetaryWorkflowMixin.planetary_footprint_points(
                {"Footprint_C0_geometry": "MULTIPOLYGON EMPTY"}
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
