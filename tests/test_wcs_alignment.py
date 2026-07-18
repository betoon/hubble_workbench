import tempfile
import unittest
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hubble_workbench_app.fits_io import stack_fits_exposures, wcs_align_fits_channels
from hubble_workbench_app.image_processing import estimate_neutral_rgb_gains


class WcsAlignmentTests(unittest.TestCase):
    def test_neutral_balance_ignores_black_border_and_reduces_color_cast(self):
        image = np.zeros((20, 20, 3), dtype=np.float32)
        image[3:17, 3:17] = (0.20, 0.10, 0.05)
        image[8:12, 8:12] = (1.0, 0.8, 0.6)

        red, green, blue = estimate_neutral_rgb_gains(image)

        self.assertLess(red, green)
        self.assertLess(green, blue)
        self.assertGreaterEqual(red, 0.5)
        self.assertLessEqual(blue, 1.8)

    def write_fits(self, path, value, crval):
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crpix = [5.5, 5.5]
        wcs.wcs.crval = list(crval)
        wcs.wcs.cdelt = [-0.001, 0.001]
        fits.PrimaryHDU(np.full((10, 10), value, dtype=np.float32), header=wcs.to_header()).writeto(path)

    def test_aligns_shifted_channels_on_union_canvas_and_reports_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            paths = [directory / f"channel_{index}.fits" for index in range(3)]
            self.write_fits(paths[0], 1, (10.000, 20.000))
            self.write_fits(paths[1], 2, (10.003, 20.000))
            self.write_fits(paths[2], 3, (10.006, 20.000))

            channels, headers, metadata = wcs_align_fits_channels(paths)

            self.assertEqual(len(channels), 3)
            self.assertTrue(all(channel.shape == channels[0].shape for channel in channels))
            self.assertGreater(channels[0].shape[1], 10)
            self.assertGreater(metadata["overlap_fraction"], 0)
            self.assertLess(metadata["overlap_fraction"], 1)
            self.assertIn("CTYPE1", headers[0])

    def test_downsamples_excessive_union_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            paths = [directory / f"channel_{index}.fits" for index in range(2)]
            self.write_fits(paths[0], 1, (10.0, 20.0))
            self.write_fits(paths[1], 2, (11.0, 20.0))
            channels, _headers, metadata = wcs_align_fits_channels(paths, max_output_pixels=100)
            self.assertGreater(metadata["pixel_scale_factor"], 1)
            self.assertLessEqual(channels[0].size, 100)

    def test_stacks_exposures_with_background_matching_and_artifact_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            paths = [directory / f"exposure_{index}.fits" for index in range(3)]
            self.write_fits(paths[0], 1, (10.0, 20.0))
            self.write_fits(paths[1], 2, (10.0, 20.0))
            self.write_fits(paths[2], 3, (10.0, 20.0))
            with fits.open(paths[1], mode="update") as hdul:
                hdul[0].data[5, 5] = 1000
            output = directory / "stacked.fits"

            output_path, metadata = stack_fits_exposures(paths, output, weights=[1, 2, 1])

            self.assertTrue(output_path.exists())
            self.assertGreater(metadata["rejected_samples"], 0)
            with fits.open(output_path) as hdul:
                self.assertEqual(hdul[0].header["NSTACK"], 3)
                self.assertEqual(hdul[1].name, "COVERAGE")
                self.assertLess(hdul[0].data[5, 5], 10)


if __name__ == "__main__":
    unittest.main()
