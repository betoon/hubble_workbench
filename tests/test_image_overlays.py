import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from hubble_workbench_app.image_overlays import load_overlay, render_overlays, start_overlay_load
from hubble_workbench_app.explorer_wizard import explorer_state, restore_explorer_state

class Var:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value

class ImageOverlayTests(unittest.TestCase):
    def make_fits(self,folder,name,shift=0):
        w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crpix=[16+shift,16]
        w.wcs.crval=[359.99,20];w.wcs.cdelt=[-.002,.002]
        yy,xx=np.mgrid[:32,:32]
        data=np.exp(-((xx-(15+shift))**2+(yy-15)**2)/6)
        data[:2,:]=np.nan
        path=Path(folder)/name;fits.PrimaryHDU(data,header=w.to_header()).writeto(path)
        return dict(source='DSS',band='red',key=name,local_path=str(path))

    def geometry(self):
        return dict(width=400,height=300,center=np.array([0,0]),scale=2000,ra0=359.99,dec0=20,cosdec=np.cos(np.deg2rad(20)))

    def test_wcs_registration_handles_offset_pixel_origins_and_ra_wrap(self):
        with tempfile.TemporaryDirectory() as folder:
            one=load_overlay(self.make_fits(folder,'one.fits'))
            two=load_overlay(self.make_fits(folder,'two.fits',shift=3))
            a=np.array(render_overlays([one],self.geometry(),'Grayscale',1,['DSS']))
            b=np.array(render_overlays([two],self.geometry(),'Grayscale',1,['DSS']))
            self.assertEqual(np.unravel_index(a[:,:,0].argmax(),a.shape[:2]),np.unravel_index(b[:,:,0].argmax(),b.shape[:2]))
            self.assertEqual(a[0,0,3],0)
            self.assertTrue((a[:,:,3]==255).any())
            self.assertIn('footprints',one['record'])

    def test_opacity_and_source_colors(self):
        with tempfile.TemporaryDirectory() as folder:
            image=load_overlay(self.make_fits(folder,'one.fits'))
            result=np.array(render_overlays([image],self.geometry(),'Source colors',.5,['DSS']))
            self.assertLessEqual(result[:,:,3].max(),128)
            point=np.unravel_index(result[:,:,2].argmax(),result.shape[:2])
            self.assertGreater(result[point][2],result[point][0])
            self.assertIsNone(render_overlays([image],self.geometry(),'Off',1,['DSS']))
            self.assertIsNone(render_overlays([image],self.geometry(),'Grayscale',0,['DSS']))

    def test_missing_local_file_is_explicit(self):
        with self.assertRaisesRegex(ValueError,'Download this image'):
            load_overlay({'local_path':'missing-overlay-test.fits'})

    def test_saved_preferences_restore_and_clear_old_cache(self):
        app=SimpleNamespace(mosaic_layer_var=Var('Image Wizard: DSS'),wizard_overlay_mode=Var('Source colors'),
            wizard_overlay_opacity=Var(.4),wizard_overlay_keys=['one'],wizard_records=[{'key':'one'}])
        saved=explorer_state(app);app.wizard_overlay_cache=['old']
        with patch('hubble_workbench_app.explorer_wizard.start_overlay_load') as loader:
            restore_explorer_state(app,saved)
            loader.assert_called_once_with(app,[{'key':'one'}],switch_tab=False)
        self.assertEqual(app.wizard_overlay_cache,[])
        self.assertEqual(app.wizard_overlay_mode.get(),'Source colors')
        restore_explorer_state(app,{})
        self.assertEqual(app.wizard_overlay_keys,[])
        self.assertEqual(app.wizard_overlay_mode.get(),'Off')

    def test_selection_limit_and_no_network_load_path(self):
        app=SimpleNamespace(wizard_busy=False,wizard_status=Var(''),wizard_start=Mock())
        start_overlay_load(app,[{'key':str(i)} for i in range(9)])
        self.assertIn('at most 8',app.wizard_status.get())
        app.wizard_start.assert_not_called()

if __name__=='__main__':unittest.main()

class OverlayRestoreIntegrationTests(unittest.TestCase):
    def test_saved_overlay_reopens_from_local_fits_without_network(self):
        import threading
        with tempfile.TemporaryDirectory() as folder:
            record=ImageOverlayTests().make_fits(folder,'restore.fits')
            app=SimpleNamespace(mosaic_layer_var=Var('Image Wizard: DSS'),wizard_overlay_mode=Var('Grayscale'),
                wizard_overlay_opacity=Var(.4),wizard_overlay_keys=[record['key']],wizard_records=[record],
                wizard_busy=False,wizard_status=Var(''),mosaic_status_var=Var(''),observatory_draw_current_mosaic=Mock())
            app.wizard_start=lambda work,finish: finish(work(threading.Event()))
            saved=explorer_state(app)
            with patch('requests.Session.get',side_effect=AssertionError('No network allowed')):
                restore_explorer_state(app,saved)
            self.assertEqual(len(app.wizard_overlay_cache),1)
            self.assertEqual(app.wizard_overlay_cache[0]['record']['key'],record['key'])
            self.assertIn('Loaded 1',app.wizard_status.get())
            self.assertEqual(app.wizard_overlay_mode.get(),'Grayscale')

    def test_old_async_result_cannot_replace_new_project(self):
        app=SimpleNamespace(wizard_busy=False,wizard_status=Var(''),wizard_start=Mock())
        start_overlay_load(app,[{'key':'old'}])
        finish=app.wizard_start.call_args.args[1]
        app.wizard_overlay_generation+=1
        app.wizard_overlay_cache=['new project']
        finish(([],[]))
        self.assertEqual(app.wizard_overlay_cache,['new project'])
