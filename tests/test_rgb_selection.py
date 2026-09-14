import unittest
from hubble_workbench_app.product_browser import ProductBrowserMixin
from hubble_workbench_app.product_scoring import ProductScoringMixin


class Picker(ProductBrowserMixin, ProductScoringMixin):
    pass


def row(channel, group="same", ra=10, detector="ACS/WFC"):
    filt = {"blue": "F435W", "green": "F555W", "red": "F814W"}[channel]
    return {"productFilename": f"hst_{group}_01_{filt}_drz.fits",
            "obs_collection": "HST", "instrument_name": detector,
            "target_name": "test", "filters": filt,
            "s_ra": ra, "s_dec": 0, "s_fov": 0.1}


class RGBSelectionTests(unittest.TestCase):
    def setUp(self):
        self.picker = Picker()

    def test_filters_from_separate_observations_can_form_set(self):
        rows = [row(ch, group=ch) for ch in ("blue", "green", "red")]
        for item in rows:
            self.assertEqual(self.picker.suggest_rgb_sets_for_rows([item]), [])
        self.assertEqual(len(self.picker.suggest_rgb_sets_for_rows(rows)), 1)

    def test_mixed_sensors_are_not_automatic_rgb(self):
        rows = [row(ch) for ch in ("blue", "green", "red")]
        rows[0]["instrument_name"] = "WFC3/UVIS"
        self.assertEqual(self.picker.suggest_rgb_sets_for_rows(rows), [])

    def test_separated_fields_rejected_even_with_same_group(self):
        rows = [row(ch) for ch in ("blue", "green", "red")]
        rows[0]["s_ra"] = 20
        self.assertEqual(self.picker.suggest_rgb_sets_for_rows(rows), [])

    def test_lower_ranked_overlapping_alternative_is_used(self):
        good = row("blue")
        bad = row("blue", ra=20)
        bad["size"] = 900000000
        selected = self.picker.suggest_rgb_sets_for_rows([bad, good, row("green"), row("red")])
        self.assertIs(selected[0]["blue"], good)

    def test_unknown_coverage_only_accepted_in_same_group(self):
        rows = [row(ch) for ch in ("blue", "green", "red")]
        for item in rows:
            item.pop("s_ra")
        self.assertEqual(len(self.picker.suggest_rgb_sets_for_rows(rows)), 1)
        rows[0]["productFilename"] = "hst_other_02_f435w_drz.fits"
        self.assertEqual(self.picker.suggest_rgb_sets_for_rows(rows), [])


if __name__ == "__main__":
    unittest.main()
