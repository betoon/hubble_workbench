import io, json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from hubble_workbench_app.archive_catalog import image_record, chandra_records, Cancelled
from hubble_workbench_app.archive_downloads import DownloadCache, validate_archive_url
from hubble_workbench_app.archive_coverage import footprint_polygons, project_polygons, align_shared
from hubble_workbench_app.image_wizard import recommend_channels

class ArchiveTests(unittest.TestCase):
    def test_alias_and_energy_order(self):
        html=''.join(f'<a href="x{i}.fits">Orion {lo}-{hi} keV Fits File</a>' for i,(lo,hi) in enumerate([(0.3,1),(1,2),(2,8)]))
        rows=chandra_records(html,'M42')
        channels=recommend_channels(rows)
        self.assertIn('0.3-1',channels['red']['band'])
        self.assertIn('2-8',channels['blue']['band'])
    def test_does_not_invent_third_band_or_mix_sources(self):
        rows=[image_record('GALEX','M51',str(w),'url'+str(w),wavelength=w) for w in [.15,.23]]
        rows.append(image_record('WISE','M51','3.4','url3',wavelength=3.4))
        self.assertFalse(recommend_channels(rows))
    def test_disjoint_polygons_and_ra_wrap(self):
        polygons=footprint_polygons('UNION (POLYGON J2000 359.9 0 0.1 0 0.1 1 POLYGON ICRS 10 0 11 0 11 1)')
        self.assertEqual(len(polygons),2)
        projected=project_polygons(polygons[:1])[0]
        self.assertLess(np.ptp(projected[:,0]),.3)
    def test_shared_crop_preserves_world_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            paths=[]
            for i in range(3):
                w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crpix=[10.5,10.5]
                w.wcs.crval=[10+i*.003,20];w.wcs.cdelt=[-.001,.001]
                path=Path(folder)/f'{i}.fits'
                fits.PrimaryHDU(np.full((20,20),i+1,dtype=np.float32),header=w.to_header()).writeto(path)
                paths.append(path)
            outputs,meta=align_shared(paths,Path(folder)/'out')
            self.assertLess(meta['output_shape'][1],20)
            for i,path in enumerate(outputs):
                data=fits.getdata(path,memmap=False)
                self.assertTrue(np.isfinite(data).any())
                np.testing.assert_allclose(data[np.isfinite(data)],i+1)
                np.testing.assert_array_equal(np.isfinite(data),np.isfinite(fits.getdata(outputs[0],memmap=False)))
                world=WCS(fits.getheader(path)).pixel_to_world(1,1)
                x,y=WCS(fits.getheader(paths[i])).world_to_pixel(world)
                self.assertTrue(0<=x<20 and 0<=y<20)

class Response:
    def __init__(self,payload,status=200,headers=None):
        self.payload=payload;self.status_code=status;self.url='https://mast.stsci.edu/test.fits'
        self.headers={'Content-Length':str(len(payload)),'ETag':'v1',**(headers or {})}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def close(self):pass
    def raise_for_status(self):
        if self.status_code>=400:raise ValueError('HTTP failure')
    def iter_content(self,chunk_size):
        yield self.payload[:2880]
        yield self.payload[2880:]

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        stream=io.BytesIO();fits.PrimaryHDU(np.ones((10,10))).writeto(stream);self.payload=stream.getvalue()
        self.session=Mock();self.session.get.return_value=Response(self.payload)
        self.cache=DownloadCache(self.tmp.name,self.session)
        self.record=image_record('Hubble','M51','F606W','https://mast.stsci.edu/test.fits')
    def test_verified_cache_avoids_network_and_detects_corruption(self):
        path=self.cache.fetch(self.record)
        self.assertEqual(path,self.cache.fetch(self.record));self.assertEqual(self.session.get.call_count,1)
        path.write_bytes(b'x'*len(self.payload))
        self.cache.fetch(self.record);self.assertEqual(self.session.get.call_count,2)
    def test_cancel_preserves_partial_and_resume(self):
        cancel=threading.Event()
        def progress(*args):cancel.set()
        with self.assertRaises(Cancelled):self.cache.fetch(self.record,cancel,progress)
        path,_=self.cache.paths(self.record)
        self.assertFalse(path.exists())
        self.assertEqual(path.with_suffix('.fits.part').stat().st_size,2880)
        cancel.clear()
        self.session.get.return_value=Response(self.payload[2880:],206,{'Content-Range':f'bytes 2880-{len(self.payload)-1}/{len(self.payload)}'})
        self.cache.fetch(self.record,cancel)
        self.assertEqual(path.read_bytes(),self.payload)
        self.assertEqual(self.session.get.call_args.kwargs['headers']['Range'],'bytes=2880-')
    def test_ignored_range_restarts_without_appending(self):
        path,_=self.cache.paths(self.record)
        path.with_suffix('.fits.part').write_bytes(b'old')
        path.with_suffix('.fits.part.json').write_text(json.dumps({'url':self.record['url'],'etag':'v1'}))
        self.cache.fetch(self.record)
        self.assertEqual(path.read_bytes(),self.payload)
    def test_range_416_restarts(self):
        path,_=self.cache.paths(self.record)
        path.with_suffix('.fits.part').write_bytes(self.payload)
        path.with_suffix('.fits.part.json').write_text(json.dumps({'url':self.record['url'],'etag':'v1'}))
        self.session.get.side_effect=[Response(b'',416),Response(self.payload)]
        self.cache.fetch(self.record)
        self.assertEqual(path.read_bytes(),self.payload)
    def test_rejects_non_image_response(self):
        self.session.get.return_value=Response(b'<html>Error</html>')
        with self.assertRaises(Exception):self.cache.fetch(self.record)
        self.assertIsNone(self.cache.cached(self.record))
    def test_rejects_unrelated_hosts(self):
        for url in ['https://nasa.gov.evil.test/file','file:///c:/a','https://user:password@nasa.gov/a']:
            with self.assertRaises(ValueError):validate_archive_url(url)

if __name__=='__main__':unittest.main()
