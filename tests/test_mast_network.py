import unittest
from types import SimpleNamespace
from unittest.mock import patch
import requests
from requests.adapters import HTTPAdapter

from hubble_workbench_app.mast_network import configure_mast_network


class MastNetworkTests(unittest.TestCase):
    def test_missing_timeout_is_bounded_and_explicit_timeout_preserved(self):
        with requests.Session() as session:
            configure_mast_network(SimpleNamespace(_session=session))
            for timeout, expected in ((None, (15, 60)), (120, 120)):
                with self.subTest(timeout=timeout), patch.object(HTTPAdapter, "send", return_value=requests.Response()) as send:
                    session.get("https://mast.stsci.edu/api/test", timeout=timeout)
                    self.assertEqual(send.call_args.kwargs["timeout"], expected)

    def test_retries_are_bounded_and_scoped_to_mast(self):
        with requests.Session() as session:
            configure_mast_network(SimpleNamespace(_session=session))
            adapter = session.get_adapter("https://mast.stsci.edu/api/v0/invoke")
            retry = adapter.max_retries
            self.assertEqual(retry.total, 2)
            self.assertIn("POST", retry.allowed_methods)
            self.assertNotIn("DELETE", retry.allowed_methods)
            self.assertIsNot(adapter, session.get_adapter("https://example.com/"))


if __name__ == "__main__":
    unittest.main()
