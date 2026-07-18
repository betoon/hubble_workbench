import tempfile
import unittest
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hubble_workbench_app.fits_io import wcs_align_fits_channels


class WcsAlignmentTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
