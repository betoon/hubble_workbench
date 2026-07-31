import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hubble_workbench_app.planetary_workflow import PlanetaryWorkflowMixin


class PlanetaryWorkflowTests(unittest.TestCase):
    def test_planetary_product_sort_is_numeric_for_scale_and_keeps_missing_last(self):
        products = [
            {"Observation_id": "A", "Map_scale": "10"},
            {"Observation_id": "B", "Map_scale": "2"},
            {"Observation_id": "C", "Map_scale": ""},
        ]
        indexed = list(enumerate(products))
        ascending = PlanetaryWorkflowMixin.sort_planetary_products(
            indexed, "scale"
        )
        descending = PlanetaryWorkflowMixin.sort_planetary_products(
            indexed, "scale", reverse=True
        )
        self.assertEqual([index for index, _product in ascending], [1, 0, 2])
        self.assertEqual([index for index, _product in descending], [0, 1, 2])

    def test_planetary_product_row_includes_instrument_target_and_scale(self):
        row = PlanetaryWorkflowMixin.planetary_product_row({
            "Observation_id": "hst-example",
            "Observation_time": "2025-01-02T03:04:05",
            "Instrument": "Hubble WFC3",
            "Target": "Uranus",
            "Map_scale": "0.25",
            "Comment": "Cloud observation",
        })
        self.assertEqual(
            row,
            (
                "hst-example", "2025-01-02", "Hubble WFC3", "Uranus",
                "0.25", "Cloud observation",
            ),
        )

    def test_opus_page_text_formats_range_and_empty_results(self):
        self.assertEqual(
            PlanetaryWorkflowMixin.planetary_opus_page_text(26, 25, 1234),
            "26-50 of 1,234",
        )
        self.assertEqual(
            PlanetaryWorkflowMixin.planetary_opus_page_text(1, 0, 0),
            "No OPUS results",
        )

    def test_opus_order_maps_user_labels_to_api_order(self):
        self.assertEqual(
            PlanetaryWorkflowMixin.planetary_opus_order("Newest first"),
            "-time1,opusid",
        )
        self.assertEqual(
            PlanetaryWorkflowMixin.planetary_opus_order("Oldest first"),
            "time1,opusid",
        )

    def test_planetary_preview_cache_is_bounded_and_refreshes_recent_item(self):
        cache = {}
        for index in range(4):
            PlanetaryWorkflowMixin.store_planetary_preview_cache(
                cache, f"preview-{index}", bytes([index + 1]), limit=3
            )
        self.assertEqual(list(cache), ["preview-1", "preview-2", "preview-3"])
        PlanetaryWorkflowMixin.store_planetary_preview_cache(
            cache, "preview-1", b"new", limit=3
        )
        self.assertEqual(list(cache), ["preview-2", "preview-3", "preview-1"])
        self.assertEqual(cache["preview-1"], b"new")

    def test_planetary_product_filter_searches_science_fields_and_keeps_indexes(self):
        products = [
            {"Observation_id": "A", "Instrument": "Voyager ISS", "Target": "Neptune"},
            {"Observation_id": "B", "Instrument": "Hubble WFC3", "Target": "Uranus"},
        ]
        self.assertEqual(
            PlanetaryWorkflowMixin.filter_planetary_products(products, "wfc3"),
            [(1, products[1])],
        )
        self.assertEqual(
            PlanetaryWorkflowMixin.filter_planetary_products(products, "neptune"),
            [(0, products[0])],
        )
        self.assertEqual(len(PlanetaryWorkflowMixin.filter_planetary_products(products)), 2)

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

    def test_lunar_url_uses_moon_target_and_lroc_codes(self):
        dataset = "LRO LROC NAC — calibrated high resolution"
        url = PlanetaryWorkflowMixin.build_planetary_ode_url(
            0.6741, 23.4730, 0.25, dataset
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["target"], ["moon"])
        self.assertEqual(query["ihid"], ["LRO"])
        self.assertEqual(query["iid"], ["LROC"])
        self.assertEqual(query["pt"], ["CDRNAC4"])

    def test_lunar_features_include_all_six_apollo_landing_sites(self):
        features = PlanetaryWorkflowMixin.MOON_FEATURES
        for mission in ("11", "12", "14", "15", "16", "17"):
            self.assertIn(f"Apollo {mission} Landing Site", features)

    def test_lunar_datasets_cover_requested_archives(self):
        names = " ".join(PlanetaryWorkflowMixin.MOON_DATASETS)
        self.assertIn("LRO", names)
        self.assertIn("Clementine", names)
        self.assertIn("Chandrayaan-1", names)

    def test_mercury_datasets_cover_messenger_mdis_imaging(self):
        names = " ".join(PlanetaryWorkflowMixin.MERCURY_DATASETS)
        self.assertIn("MESSENGER", names)
        self.assertIn("NAC", names)
        self.assertIn("WAC", names)

    def test_mercury_url_uses_messenger_mdis_codes(self):
        dataset = "MESSENGER MDIS NAC — calibrated high resolution"
        url = PlanetaryWorkflowMixin.build_planetary_ode_url(
            30.5, 162.7, 0.5, dataset
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["target"], ["mercury"])
        self.assertEqual(query["ihid"], ["MESSENGER"])
        self.assertEqual(query["iid"], ["MDIS-NAC"])
        self.assertEqual(query["pt"], ["CDRNAC"])

    def test_mercury_sources_include_messenger_and_bepicolombo(self):
        names = " ".join(source[0] for source in PlanetaryWorkflowMixin.PLANETARY_SOURCES)
        self.assertIn("MESSENGER", names)
        self.assertIn("BepiColombo", names)

    def test_full_planet_views_cover_every_supported_world(self):
        self.assertEqual(
            set(PlanetaryWorkflowMixin.PLANETARY_FULL_VIEW_URLS),
            set(PlanetaryWorkflowMixin.PLANETARY_FEATURES),
        )
        for url in PlanetaryWorkflowMixin.PLANETARY_FULL_VIEW_URLS.values():
            self.assertTrue(
                url.startswith("https://trek.nasa.gov/")
                or url.startswith("https://eyes.nasa.gov/")
            )

    def test_venus_url_uses_magellan_radar_codes(self):
        dataset = "Magellan SAR — full-resolution radar mosaics"
        url = PlanetaryWorkflowMixin.build_planetary_ode_url(
            0.5, 194.5, 0.5, dataset
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["target"], ["venus"])
        self.assertEqual(query["ihid"], ["MGN"])
        self.assertEqual(query["iid"], ["RDRS"])
        self.assertEqual(query["pt"], ["FMIDR"])

    def test_outer_planets_use_official_external_archives(self):
        for planet in ("Jupiter", "Saturn", "Uranus", "Neptune"):
            datasets = PlanetaryWorkflowMixin.PLANETARY_DATASETS[planet]
            self.assertGreaterEqual(len(datasets), 4)
            self.assertTrue(any("opus_query" in dataset for dataset in datasets.values()))
            for dataset in datasets.values():
                self.assertTrue("opus_query" in dataset or "external_url" in dataset)

    def test_ice_giants_offer_voyager_hubble_and_webb_sources(self):
        for planet in ("Uranus", "Neptune"):
            datasets = PlanetaryWorkflowMixin.PLANETARY_DATASETS[planet]
            names = " ".join(datasets)
            self.assertIn("Voyager", names)
            self.assertIn("Hubble", names)
            self.assertIn("JWST", names)
            self.assertTrue(
                any(
                    dataset.get("opus_query", {}).get("planet") == planet
                    for dataset in datasets.values()
                )
            )

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

    def test_ode_response_accepts_empty_product_marker(self):
        payload = {
            "ODEResults": {
                "Status": "Success",
                "Products": "No Products Found",
            }
        }
        self.assertEqual(PlanetaryWorkflowMixin.parse_mars_ode_response(payload), [])

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

    def test_files_url_uses_specific_archive_product_id(self):
        url = PlanetaryWorkflowMixin.build_mars_files_url({
            "Observation_id": "ESP_TEST",
            "ProductURL": "https://ode.example/product?product_id=ESP_TEST_COLOR",
        })
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["query"], ["product"])
        self.assertEqual(query["results"], ["mf"])
        self.assertEqual(query["pdsid"], ["ESP_TEST_COLOR"])

    def test_parse_product_files_accepts_single_or_list_and_filters_bad_urls(self):
        payload = {
            "ODEResults": {
                "Status": "Success",
                "Products": {
                    "Product": {
                        "Product_files": {
                            "Product_file": [
                                {"FileName": "image.jp2", "URL": "https://example.invalid/image.jp2"},
                                {"FileName": "missing.jp2", "URL": ""},
                            ]
                        }
                    }
                },
            }
        }
        files = PlanetaryWorkflowMixin.parse_planetary_product_files(payload)
        self.assertEqual([item["FileName"] for item in files], ["image.jp2"])

    def test_planetary_file_size_text(self):
        self.assertEqual(PlanetaryWorkflowMixin.planetary_file_size_text(512), "512 KB")
        self.assertEqual(PlanetaryWorkflowMixin.planetary_file_size_text(2048), "2.0 MB")
        self.assertEqual(
            PlanetaryWorkflowMixin.planetary_file_size_text(2 * 1024 * 1024),
            "2.00 GB",
        )

    def test_unique_destination_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "mars.jp2"
            first.write_bytes(b"existing")
            destination = PlanetaryWorkflowMixin.unique_planetary_destination(folder, "mars.jp2")
            self.assertEqual(destination.name, "mars_2.jp2")


if __name__ == "__main__":
    unittest.main()
