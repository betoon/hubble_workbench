import unittest

from hubble_workbench_app.download_workflow import DownloadWorkflowMixin


class DownloadRoutingTests(unittest.TestCase):
    def test_hla_http_product_uses_direct_url(self):
        kind, source = DownloadWorkflowMixin.download_row_source({
            "_source": "HLA",
            "URL": "https://hla.stsci.edu/file.fits",
        })
        self.assertEqual(kind, "url")
        self.assertEqual(source, "https://hla.stsci.edu/file.fits")

    def test_mast_product_without_url_uses_data_uri(self):
        kind, source = DownloadWorkflowMixin.download_row_source({
            "URL": "",
            "dataURI": "mast:HST/product/example_drc.fits",
        })
        self.assertEqual(kind, "mast")
        self.assertEqual(source, "mast:HST/product/example_drc.fits")

    def test_product_without_any_location_is_marked_missing(self):
        self.assertEqual(
            DownloadWorkflowMixin.download_row_source({"productFilename": "missing.fits"}),
            ("missing", ""),
        )


if __name__ == "__main__":
    unittest.main()
