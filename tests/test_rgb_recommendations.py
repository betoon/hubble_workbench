import tempfile
import unittest
from pathlib import Path
from hubble_workbench_app.rgb_recommendations import recommend_rgb


def row(band, **extra):
    return dict(source='Spitzer', instrument='IRAC', target='M51', band=str(band),
                wavelength=float(band), key=str(band), **extra)

class RGBRecommendationTests(unittest.TestCase):
    def test_mosaics_win_over_first_exposures(self):
        exposures=[row(i,product_type='calibrated exposure') for i in (1,2,3)]
        mosaics=[dict(r,key=r['key']+'m',product_type='mosaic') for r in exposures]
        channels,reason=recommend_rgb(exposures+mosaics)
        self.assertTrue(all(r['product_type']=='mosaic' for r in channels.values()))
        self.assertIn('3/3 mosaic',reason)
        self.assertEqual(channels['red']['wavelength'],3)
        self.assertEqual(channels['blue']['wavelength'],1)

    def test_target_and_instrument_boundaries(self):
        for field in ('target','instrument','source'):
            rows=[row(i) for i in (1,2,3)]
            rows[2][field]='different'
            self.assertFalse(recommend_rgb(rows)[0])

    def test_distinct_files_required_even_for_named_channels(self):
        rows=[dict(row(i), key='same', channel=ch) for i,ch in zip((1,2,3),('red','green','blue'))]
        self.assertFalse(recommend_rgb(rows)[0])

    def test_existing_local_file_breaks_quality_tie(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'local.fits';path.write_bytes(b'fixture')
            rows=[row(i) for i in (1,2,3)]
            cached=dict(rows[0],key='cached',local_path=str(path))
            channels,reason=recommend_rgb(rows+[cached])
            self.assertEqual(channels['blue']['key'],'cached')
            self.assertIn('1/3 local',reason)

    def test_missing_file_does_not_gain_preference(self):
        rows=[row(i) for i in (1,2,3)]
        channels,reason=recommend_rgb(rows+[dict(rows[0],key='zmissing',local_path='absent-xyz.fits')])
        self.assertEqual(channels['blue']['key'],'1')
        self.assertIn('0/3 local',reason)

    def test_order_independent_and_invalid_wavelengths_ignored(self):
        rows=[row(i) for i in (1,2,3)]+[dict(row(4),wavelength='unknown')]
        self.assertEqual(recommend_rgb(rows)[0],recommend_rgb(list(reversed(rows)))[0])

    def test_named_chandra_channels_preserve_energy_mapping(self):
        rows=[dict(row(i),channel=ch,wavelength=None) for i,ch in zip((1,2,3),('red','green','blue'))]
        channels,_=recommend_rgb(rows)
        self.assertEqual(channels['red']['band'],'1')

if __name__=='__main__':unittest.main()
