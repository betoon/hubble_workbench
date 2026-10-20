import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from hubble_workbench_app.explorer_wizard import layer_records, draw_wizard_layer, select_wizard_footprint, explorer_state, restore_explorer_state
from hubble_workbench_app.observatory_workflow import ObservatoryWorkflowMixin

class Var:
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value

class ExplorerWizardTests(unittest.TestCase):
    def app(self, records):
        canvas = Mock()
        canvas.winfo_width.return_value = 700
        canvas.winfo_height.return_value = 500
        return SimpleNamespace(mosaic_canvas=canvas, mosaic_layer_var=Var('Image Wizard: All'),
            mosaic_status_var=Var(''), wizard_records=records,
            observatory_point_in_polygon=ObservatoryWorkflowMixin.observatory_point_in_polygon)

    def test_layers_filter_aliases_and_keep_all_sources(self):
        rows = [{'source':'HST'}, {'source':'WISE'}, {'source':'JWST'}]
        self.assertEqual(layer_records(rows, 'Image Wizard: Hubble'), rows[:1])
        self.assertEqual(layer_records(rows, 'Image Wizard: All'), rows)
        self.assertEqual(layer_records(rows, 'Image Wizard: GALEX'), [])

    def test_requested_actual_unknown_and_ra_wrap(self):
        rows = [dict(source='DSS', ra=359.99, dec=0, field_deg=.1),
                dict(source='WISE', footprints=[[[359.9,0],[.1,0],[.1,.1],[359.9,.1]]]),
                dict(source='GALEX')]
        app=self.app(rows)
        draw_wizard_layer(app)
        self.assertEqual(len(app.wizard_mosaic_polygons), 2)
        self.assertIn('1 without drawable coverage', app.mosaic_status_var.get())
        calls=app.mosaic_canvas.create_polygon.call_args_list
        self.assertEqual(calls[0].kwargs['dash'], (4,3))
        self.assertEqual(calls[1].kwargs['dash'], ())
        for call in calls:
            self.assertTrue(all(0 <= x <= 700 for x in call.args))

    def test_wide_canvas_centers_coverage_and_labels_source(self):
        app = self.app([dict(source='WISE', band='W1', footprints=[[[10,0],[11,0],[11,1],[10,1]]])])
        app.mosaic_canvas.winfo_width.return_value = 1400
        draw_wizard_layer(app)
        points = app.wizard_mosaic_polygons[0]['points']
        self.assertAlmostEqual((min(p[0] for p in points)+max(p[0] for p in points))/2, 700)
        self.assertTrue(any(c.kwargs.get('text') == 'WISE / W1'
                            for c in app.mosaic_canvas.create_text.call_args_list))

    def test_click_opens_matching_wizard_record(self):
        row={'source':'WISE', 'footprints':[[[10,0],[11,0],[11,1],[10,1]]]}
        app=self.app([row]);draw_wizard_layer(app)
        app.wizard_tree=Mock();app.wizard_review=Mock();app.notebook=Mock();app.wizard_tab='wizard'
        points=app.wizard_mosaic_polygons[0]['points']
        event=SimpleNamespace(x=sum(p[0] for p in points)/4, y=sum(p[1] for p in points)/4)
        self.assertEqual(select_wizard_footprint(app,event), row)
        app.notebook.select.assert_called_once_with('wizard')
        app.wizard_tree.selection_set.assert_called_once_with('0')

    def test_layer_roundtrip_and_old_project_default(self):
        app=self.app([]);app.mosaic_layer_var.set('Image Wizard: WISE')
        state=explorer_state(app);app.observatory_draw_current_mosaic=Mock()
        app.mosaic_layer_var.set('JWST');restore_explorer_state(app,state)
        self.assertEqual(app.mosaic_layer_var.get(),'Image Wizard: WISE')
        restore_explorer_state(app,{})
        self.assertEqual(app.mosaic_layer_var.get(),'All active sources')
        restore_explorer_state(app,{'layer':'unknown'})
        self.assertEqual(app.mosaic_layer_var.get(),'All active sources')


class ProjectReopenTests(unittest.TestCase):
    def test_project_roundtrip_and_legacy_clear(self):
        from hubble_workbench_app.project_workflow import ProjectWorkflowMixin
        class App(ProjectWorkflowMixin):
            def wizard_state(self):
                return {'records': self.wizard_records, 'channels': self.wizard_channels}
            def wizard_restore(self, data):
                self.wizard_records = data.get('records', [])
                self.wizard_channels = data.get('channels', {})
        app = App()
        for name in ('target radius compose_stretch red_path green_path blue_path composite_size high_quality prefer_drizzled '
                     'use_fits_liberator presentation_cleanup straighten_angle auto_crop_presentation auto_compose '
                     'black_point brightness contrast saturation red_balance green_balance blue_balance').split():
            setattr(app, name + '_var', Var(1))
        app.channel_stretch_vars = {}
        app.compose_status = Var('')
        app.mosaic_layer_var = Var('Image Wizard: GALEX')
        app.wizard_records = [{'source':'GALEX', 'key':'uv', 'local_path':'missing-test-file.fits'}]
        app.wizard_channels = {'blue': app.wizard_records[0]}
        saved = app.project_state()
        app.wizard_records = []
        app.apply_project_state(saved)
        self.assertEqual(app.mosaic_layer_var.get(), 'Image Wizard: GALEX')
        self.assertEqual(app.wizard_channels['blue']['key'], 'uv')
        self.assertIn('1 Wizard file(s) missing', app.compose_status.get())
        app.apply_project_state({'target':'old project'})
        self.assertEqual(app.wizard_records, [])
        self.assertEqual(app.wizard_channels, {})
        self.assertEqual(app.mosaic_layer_var.get(), 'All active sources')

if __name__ == '__main__': unittest.main()
