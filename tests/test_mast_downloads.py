import unittest
from unittest.mock import patch

from astroquery.mast import Observations
from astropy.table import Table

from hubble_workbench_app.mast_products import mast_product_table


class MastDownloadTests(unittest.TestCase):
    def test_selected_products_reach_download_without_observation_lookup(self):
        rows = [
            {"dataURI": f"mast:HST/product/{name}.fits",
             "productFilename": f"{name}.fits", "obs_id": "same-observation",
             "obs_collection": "HST", "productGroupDescription": "Minimum Recommended Products"}
            for name in ("blue", "green", "red", "extra")
        ]
        for count in (1, 3, 4):
            with self.subTest(count=count):
                products = mast_product_table(rows[:count])
                self.assertIsInstance(products, Table)
                with patch.object(Observations, "get_product_list", side_effect=AssertionError("Unexpected observation lookup")), patch.object(Observations, "_download_files", return_value="manifest") as download:
                    result = Observations.download_products(products, download_dir="test-downloads", cache=True)
                self.assertEqual(result, "manifest")
                selected = download.call_args.args[0]
                self.assertEqual(set(selected["dataURI"]), {row["dataURI"] for row in rows[:count]})
                self.assertTrue(download.call_args.kwargs["cache"])
        self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
