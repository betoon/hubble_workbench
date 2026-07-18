import unittest

import numpy as np

from hubble_workbench_app.hydrogen_processing import HYDROGEN_PRESETS, process_hydrogen_rgb
from hubble_workbench_app.hydrogen_workflow import HydrogenWorkflowMixin


class HydrogenProcessingTests(unittest.TestCase):
    def test_rapid_preview_requests_are_debounced(self):
        class PreviewHarness(HydrogenWorkflowMixin):
            def __init__(self):
                self.hydrogen_preview_rgb = np.zeros((2, 2, 3), dtype=np.float32)
                self.cancelled = []
                self.scheduled = []

            def after(self, delay, callback):
                job = f"job-{len(self.scheduled) + 1}"
                self.scheduled.append((job, delay, callback))
                return job

            def after_cancel(self, job):
                self.cancelled.append(job)

        harness = PreviewHarness()
        harness.hydrogen_schedule_preview()
        harness.hydrogen_schedule_preview()

        self.assertEqual(harness.cancelled, ["job-1"])
        self.assertEqual(len(harness.scheduled), 2)
        self.assertEqual(harness.scheduled[-1][1], 180)
        self.assertEqual(harness.scheduled[-1][2], harness.hydrogen_update_preview)

    def test_compact_red_blue_structure_is_enhanced_and_background_is_preserved(self):
        image = np.full((41, 41, 3), 0.05, dtype=np.float32)
        image[18:23, 18:23, 0] = 0.8
        image[18:23, 18:23, 2] = 0.7

        enhanced, mask = process_hydrogen_rgb(
            image,
            mask_background=False,
            sky_percentile=0,
            stretch_factor=1,
            preset="Natural H-Alpha Red",
            glow_strength=1.0,
            kernel_size=9,
            smooth=False,
        )

        self.assertGreater(mask[20, 20], mask[0, 0])
        self.assertGreater(enhanced[20, 20, 0], enhanced[20, 20, 1])
        self.assertEqual(enhanced.shape, image.shape)

    def test_border_mask_and_presets_are_available(self):
        image = np.zeros((20, 20, 3), dtype=np.float32)
        image[5:15, 5:15] = (0.4, 0.2, 0.4)
        enhanced, mask = process_hydrogen_rgb(image, background_color=(0, 0, 0), tolerance=2)

        self.assertTrue(np.all(enhanced[0, 0] == 0))
        self.assertEqual(mask[0, 0], 0)
        self.assertIn("Vibrant Magenta/Pink", HYDROGEN_PRESETS)

    def test_channel_scales_change_the_stretched_composite(self):
        image = np.full((15, 15, 3), 0.1, dtype=np.float32)
        image[6:9, 6:9] = 0.2
        normal, _mask = process_hydrogen_rgb(image, mask_background=False, sky_percentile=0, stretch_factor=1, glow_strength=0)
        scaled, _mask = process_hydrogen_rgb(
            image,
            mask_background=False,
            sky_percentile=0,
            stretch_factor=1,
            glow_strength=0,
            channel_scales=(1.5, 1.0, 1.0),
        )
        self.assertGreater(scaled[7, 7, 0], normal[7, 7, 0])


if __name__ == "__main__":
    unittest.main()
