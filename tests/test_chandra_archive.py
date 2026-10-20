import unittest
from unittest.mock import Mock, patch
import threading
from hubble_workbench_app.chandra_archive import parse_chandra_images, search_chandra_archive, ENDPOINT


def votable(rows='', status='OK'):
    fields = ''.join(f'<FIELD name="{name}" datatype="char" arraysize="*"/>' for name in
                     ('accref','imgfmt','obsid','instrument','name','bandlo','bandhi','filesize','exptime','ra','dec','date_obs'))
    return (f'<VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE>'
            f'<INFO name="QUERY_STATUS" value="{status}"/>'
            f'<TABLE>{fields}<DATA><TABLEDATA>{rows}</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>').encode()

def row(url='https://cdaftp.cfa.harvard.edu/image.fits', fmt='image/fits'):
    values=(url,fmt,'123','ACIS-I','Archive name','.2','20','2048','5','201','-43','58000')
    return '<TR>'+''.join(f'<TD>{v}</TD>' for v in values)+'</TR>'

class ChandraArchiveTests(unittest.TestCase):
    def test_metadata_units_deduplication_and_fits_only(self):
        records=parse_chandra_images(votable(row()+row()+row(fmt='image/jpeg')),'Requested target')
        self.assertEqual(len(records),1)
        r=records[0]
        self.assertEqual(r['target'],'Requested target')
        self.assertEqual(r['observation_target'],'Archive name')
        self.assertEqual(r['exposure_seconds'],5000)
        self.assertEqual(r['size'],2048)
        self.assertEqual(r['footprint_kind'],'unknown')
        self.assertNotIn('footprints',r)
        self.assertIn('Obs 123',r['display_label'])
        self.assertAlmostEqual(r['wavelength'],.00123984/10.1)

    def test_service_error_and_truncation_are_visible(self):
        for status in ('ERROR','OVERFLOW'):
            with self.assertRaises(ValueError):parse_chandra_images(votable(status=status),'x')

    def test_empty_results(self):
        self.assertEqual(parse_chandra_images(votable(),'x'),[])

    def test_untrusted_download_reference_rejected(self):
        with self.assertRaises(ValueError):parse_chandra_images(votable(row(url='https://untrusted.example/image.fits')),'x')

    def test_replacement_endpoint_parameters_and_cancel(self):
        response=Mock(content=votable(row()))
        session=Mock();session.get.return_value=response
        session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
        with patch('hubble_workbench_app.archive_catalog.network_session',return_value=session):
            self.assertEqual(len(search_chandra_archive('x',10,20,6)),1)
        args=session.get.call_args
        self.assertEqual(args.args[0],ENDPOINT)
        self.assertEqual(args.kwargs['params']['SIZE'],.1)
        event=threading.Event();event.set()
        from hubble_workbench_app.archive_catalog import Cancelled
        with self.assertRaises(Cancelled):search_chandra_archive('x',10,20,6,event)

if __name__=='__main__':unittest.main()
