import json
import tempfile
import threading
import unittest
from pathlib import Path
import numpy as np
from astropy.wcs import WCS
from hubble_workbench_app.portable_projects import export_portable_project, load_project_document
from hubble_workbench_app.resolution_matching import match_resolution, validate_resolution
from hubble_workbench_app.overlay_controls import move_layer, ordered_overlays, layer_settings
import test_image_overlays
from hubble_workbench_app.image_overlays import load_overlay, render_overlays

class PortableTests(unittest.TestCase):
    def test_move_deduplicate_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'original.fits';source.write_bytes(b'FITS test data')
            record={'key':'https://example/image','local_path':str(source)}
            state={'red':str(source),'green':str(source),'image_wizard':{'records':[record],'channels':{'red':record}},'archive_provenance':{'aligned_paths':[str(source)],'run_directory':str(root)}}
            project=export_portable_project(state,root/'bundle')
            self.assertEqual(len(list((project.parent/'data').iterdir())),1)
            self.assertEqual(state['red'],str(source))
            project.parent.rename(root/'moved');source.unlink()
            loaded=load_project_document(root/'moved/project.json')
            self.assertTrue(Path(loaded['red']).is_file())
            self.assertEqual(loaded['red'],loaded['image_wizard']['channels']['red']['local_path'])
            self.assertEqual(loaded['image_wizard']['records'][0]['key'],'https://example/image')
            Path(loaded['red']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):load_project_document(root/'moved/project.json')
    def test_missing_cancelled_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'a.fits';p.write_bytes(b'x')
            with self.assertRaises(FileNotFoundError):export_portable_project({'red':str(root/'missing.fits')},root/'missing')
            cancel=threading.Event();cancel.set()
            with self.assertRaises(Exception):export_portable_project({'red':str(p)},root/'cancel',cancel)
            self.assertFalse((root/'cancel').exists())
            project=export_portable_project({'red':str(p)},root/'bundle')
            data=json.loads(project.read_text());data['red']='../a.fits';project.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'outside'):load_project_document(project)
    def test_legacy_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'project.json';p.write_text('{"red":"local.fits"}')
            self.assertEqual(load_project_document(p)['red'],str(Path(tmp)/'local.fits'))

class ResolutionTests(unittest.TestCase):
    def header(self):
        w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crpix=[51,51];w.wcs.crval=[10,20];w.wcs.cdelt=[-1/3600,1/3600]
        return w.to_header()
    def test_gaussian_width_and_nan_mask(self):
        yy,xx=np.mgrid[-50:51,-50:51];sigma=2/np.sqrt(8*np.log(2))
        image=np.exp(-(xx**2+yy**2)/(2*sigma**2));image[0]=np.nan
        result,meta=match_resolution([image,image],[self.header(),self.header()],[2,6])
        measured=np.sqrt(np.nansum(result[0]*xx**2)/np.nansum(result[0]))*np.sqrt(8*np.log(2))
        self.assertAlmostEqual(measured,6,places=2)
        np.testing.assert_array_equal(result[1],image)
        self.assertTrue(np.isnan(result[0][0]).all())
        self.assertEqual(meta['target_fwhm_arcsec'],6)
    def test_flat_field_edges_and_disabled(self):
        image=np.ones((101,101));image[:20]=np.nan
        result,_=match_resolution([image,image],[self.header(),self.header()],[1,4])
        np.testing.assert_allclose(result[0][20:],1,atol=1e-6)
        result,meta=match_resolution([image],[self.header()],None)
        self.assertIs(result[0],image);self.assertEqual(meta,{})
    def test_invalid_and_excessive(self):
        for values in ([0,2],[-1,2],[float('nan'),2],[1]):
            with self.assertRaises(ValueError):validate_resolution(values,2)
        with self.assertRaisesRegex(ValueError,'64 pixels'):match_resolution([np.ones((3,3))]*2,[self.header()]*2,[1,1000])

class LayerTests(unittest.TestCase):
    def test_order_and_sanitization(self):
        self.assertEqual(move_layer(['a','b'],'a',1),['b','a'])
        self.assertEqual(move_layer(['a','b'],'a',-1),['a','b'])
        self.assertEqual(layer_settings({'a':{'opacity':float('nan')}},'a')['opacity'],1)
        self.assertEqual([x['record']['key'] for x in ordered_overlays([{'record':{'key':'a'}},{'record':{'key':'b'}}],['b','a'])],['b','a'])
    def test_visibility_and_individual_alpha(self):
        helper=test_image_overlays.ImageOverlayTests()
        with tempfile.TemporaryDirectory() as tmp:
            image=load_overlay(helper.make_fits(tmp,'a.fits'))
            result=render_overlays([image],helper.geometry(),'Grayscale',1,['DSS'],{'a.fits':{'visible':False}})
            self.assertEqual(np.array(result)[:,:,3].max(),0)
            result=render_overlays([image],helper.geometry(),'Grayscale',.5,['DSS'],{'a.fits':{'opacity':.5}})
            self.assertLessEqual(np.array(result)[:,:,3].max(),64)

class WorkflowIntegrationTests(unittest.TestCase):
    def test_four_channel_match_bundle_move_and_compose_offline(self):
        from astropy.io import fits
        from hubble_workbench_app.archive_coverage import align_shared
        from hubble_workbench_app.compose_workflow import ComposeWorkflowMixin
        from test_luminance import Var
        from unittest.mock import patch
        class App(ComposeWorkflowMixin):
            def after(self,*args):pass
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths=[];yy,xx=np.mgrid[:32,:32]
            for index in range(4):
                path=root/f'channel{index}.fits'
                fits.PrimaryHDU((xx+(index+1)*yy+1).astype(float),header=ResolutionTests().header()).writeto(path)
                paths.append(str(path))
            aligned,metadata=align_shared(paths,root/'aligned',resolution=[1,2,3,4])
            self.assertEqual(metadata['resolution_matching']['target_fwhm_arcsec'],4)
            self.assertEqual(fits.getheader(aligned[0])['PSFFWHM'],4)
            state=dict(zip(('red','green','blue'),aligned[:3]))
            state['archive_provenance']={'aligned_paths':aligned,'luminance':{'strength':.5},'alignment':metadata}
            state['image_wizard']={'records':[{'local_path':p} for p in paths]}
            export_portable_project(state,root/'bundle');(root/'bundle').rename(root/'relocated')
            with patch('requests.Session.get',side_effect=AssertionError('offline')):
                loaded=load_project_document(root/'relocated/project.json')
                app=App();app.high_quality_var=Var(True);app.compose_stretch_var=Var('asinh');app.composite_size_var=Var('Largest channel')
                app.channel_stretch_vars={ch:{'low':Var(.2),'high':Var(99.8),'gamma':Var(1),'asinh':Var(12)} for ch in ('red','green','blue')}
                app.archive_provenance=loaded['archive_provenance']
                result=app.compose_rgb_from_paths([loaded[ch] for ch in ('red','green','blue')])
            self.assertEqual(result[4].shape[-1],3);self.assertIn('LRGB',result[5])
            self.assertTrue(np.isfinite(result[4]).all())
