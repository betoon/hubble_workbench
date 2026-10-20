import tempfile
import unittest
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from hubble_workbench_app.luminance import blend_luminance, luminance_settings
from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin

class Var:
    def __init__(self,v):self.v=v
    def get(self):return self.v
    def set(self,v):self.v=v

class LuminanceTests(unittest.TestCase):
    def test_zero_strength_and_mask_leave_pixels_unchanged(self):
        rgb=np.full((2,2,3),.2,dtype=np.float32)
        np.testing.assert_array_equal(blend_luminance(rgb,np.ones((2,2)),0),rgb)
        valid=np.array([[True,False],[False,False]])
        out=blend_luminance(rgb,np.ones((2,2))*.7,1,valid)
        np.testing.assert_allclose(out[0,0],.7)
        np.testing.assert_array_equal(out[~valid],rgb[~valid])

    def test_hue_and_missing_pixels_preserved(self):
        rgb=np.array([[[.2,.4,.1],[0,0,0],[.3,.2,.1]]],dtype=np.float32)
        out=blend_luminance(rgb,np.array([[1,1,np.nan]]),1)
        self.assertAlmostEqual(out[0,0,0]/out[0,0,1],.5)
        self.assertLessEqual(out.max(),1)
        np.testing.assert_array_equal(out[0,1:],rgb[0,1:])

    def test_unrelated_rgb_cannot_inherit_luminance(self):
        provenance={'aligned_paths':['r','g','b','l'],'luminance':{'strength':.5}}
        self.assertIsNone(luminance_settings(provenance,['other','g','b']))
        self.assertEqual(luminance_settings(provenance,['r','g','b'])['path'],'l')
        self.assertIsNone(luminance_settings({},['r','g','b']))

    def test_invalid_strength_and_shape_rejected(self):
        for strength in (-1,2,np.nan):
            with self.assertRaises(ValueError):blend_luminance(np.ones((2,2,3)),np.ones((2,2)),strength)
        with self.assertRaises(ValueError):blend_luminance(np.ones((2,2,3)),np.ones((3,3)),.5)

    def test_four_fits_composition_and_missing_l_fail_closed(self):
        class App(ComposeWorkflowMixin):
            def after(self,*args):pass
        with tempfile.TemporaryDirectory() as folder:
            w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crpix=[10,10];w.wcs.crval=[10,20];w.wcs.cdelt=[-.001,.001]
            yy,xx=np.mgrid[:20,:20]
            paths=[]
            for i,data in enumerate((xx+yy+1,xx+2*yy+1,2*xx+yy+1,(xx-10)**2+(yy-10)**2+1)):
                path=Path(folder)/f'{i}.fits';fits.PrimaryHDU(data.astype(float),header=w.to_header()).writeto(path);paths.append(str(path))
            app=App();app.high_quality_var=Var(True);app.compose_stretch_var=Var('asinh');app.composite_size_var=Var('Largest channel')
            app.channel_stretch_vars={ch:{'low':Var(.2),'high':Var(99.8),'gamma':Var(1),'asinh':Var(12)} for ch in ('red','green','blue')}
            app.archive_provenance={'aligned_paths':paths,'luminance':{'strength':0}}
            baseline=app.compose_rgb_from_paths(paths[:3])[4]
            app.archive_provenance['luminance']['strength']=.8
            result=app.compose_rgb_from_paths(paths[:3])
            self.assertEqual(result[4].shape,baseline.shape)
            self.assertFalse(np.allclose(result[4],baseline))
            self.assertIn('LRGB',result[5]);self.assertEqual(len(result[1]),3)
            app.archive_provenance['aligned_paths'][3]=str(Path(folder)/'missing.fits')
            with self.assertRaisesRegex(ValueError,'LRGB requires valid WCS'):app.compose_rgb_from_paths(paths[:3])

if __name__=='__main__':unittest.main()

class WizardLuminanceStateTests(unittest.TestCase):
    def test_assignment_strength_roundtrip_and_legacy_default(self):
        from hubble_workbench_app.image_wizard import ImageWizardMixin
        class App(ImageWizardMixin):
            def wizard_refresh(self):pass
        app=App()
        for name,value in [('target','M51'),('source','DSS'),('field','5'),('pixels','512'),('shared',True),('luminance_strength',.7),('source_help','')]:
            setattr(app,'wizard_'+name,Var(value))
        app.wizard_records=[{'source':'DSS','band':'red','key':'l'}]
        app.wizard_channels={'luminance':app.wizard_records[0]}
        saved=app.wizard_state()
        app.wizard_restore({})
        self.assertEqual(app.wizard_luminance_strength.get(),.5)
        self.assertEqual(app.wizard_channels,{})
        app.wizard_restore(saved)
        self.assertEqual(app.wizard_luminance_strength.get(),.7)
        self.assertEqual(app.wizard_channels['luminance']['key'],'l')

    def test_invalid_strength_stops_before_download(self):
        from hubble_workbench_app.image_wizard import ImageWizardMixin
        from unittest.mock import Mock
        class App(ImageWizardMixin):pass
        app=App();app.wizard_channels={ch:{} for ch in ('red','green','blue','luminance')}
        app.wizard_luminance_strength=Var(float('nan'));app.wizard_status=Var('');app.wizard_start=Mock()
        app.wizard_build()
        app.wizard_start.assert_not_called()
        self.assertIn('between 0 and 1',app.wizard_status.get())
