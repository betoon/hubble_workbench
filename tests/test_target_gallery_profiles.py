import unittest
from collections import defaultdict

from hubble_workbench_app.catalogs import (
    JWST_TARGET_GALLERY,
    TARGET_GALLERY,
    TARGET_RECIPES,
    TARGET_SEARCH_PROFILES,
)
from hubble_workbench_app.mast_helpers import MastSearchHelperMixin
from hubble_workbench_app.target_gallery import TargetGalleryMixin


class TargetGalleryProfileTests(unittest.TestCase):
    def test_gallery_targets_do_not_duplicate_labels(self):
        for gallery in (TARGET_GALLERY, JWST_TARGET_GALLERY):
            targets = defaultdict(list)
            for label, target, _radius in gallery:
                targets[target].append(label)
            duplicates = {target: labels for target, labels in targets.items() if len(labels) > 1}
            self.assertEqual(duplicates, {})

    def test_pillars_gallery_uses_friendly_target_name(self):
        hst_entry = next(item for item in TARGET_GALLERY if "Pillars of Creation" in item[0])
        jwst_entry = next(item for item in JWST_TARGET_GALLERY if item[0] == "Pillars of Creation")
        self.assertEqual(hst_entry[1], "Pillars of Creation")
        self.assertEqual(jwst_entry[1], "Pillars of Creation")
        self.assertEqual(hst_entry[2], "0.035 deg")

    def test_pillars_alias_maps_to_focused_search_profile(self):
        profile = MastSearchHelperMixin.target_search_profile("Pillars of Creation")
        self.assertEqual(profile, TARGET_SEARCH_PROFILES["M16-PILLARS"])
        self.assertEqual(profile["coordinate"], "18h18m48s -13d49m00s")
        self.assertIn("M16", MastSearchHelperMixin.target_name_variants("Pillars of Creation"))

    def test_pillars_friendly_name_uses_specific_recipe(self):
        recipe = TargetGalleryMixin().target_recipe("Pillars of Creation")
        self.assertEqual(recipe, TARGET_RECIPES["M16-PILLARS"])
        self.assertEqual(recipe["name"], "Pillars of Creation / Fingers of God")


if __name__ == "__main__":
    unittest.main()