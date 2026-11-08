"""Executed on GitHub CI where Streamlit is installed; verifies first browser session."""
from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


@unittest.skipUnless(AppTest is not None,'Streamlit testing framework unavailable in offline build')
class StreamlitAppTests(unittest.TestCase):
    def test_r05_multi_column_main_starts_with_overview(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        self.assertFalse(app.exception, f'R0.5 entrypoint crashed: {list(app.exception)}')
        self.assertFalse(app.error, f'R0.5 entrypoint error: {list(app.error)}')
        self.assertEqual(len(app.session_state['project']['columns']), 1)
        self.assertTrue(any('Обзор проекта' in x.value for x in app.title))

    def test_default_session_presents_reference_without_mode_selector(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'legacy_single_column.py'),default_timeout=60).run()
        self.assertFalse(app.exception, f'Streamlit crashed: {list(app.exception)}')
        self.assertFalse(app.error, f'Streamlit error: {list(app.error)}')
        # The original two-mode radio must not reappear.
        radio_labels=[getattr(item,'label','') for item in app.radio]
        self.assertNotIn('Calculation model',radio_labels)
        self.assertTrue(any('Calculated results' in x.value for x in app.subheader))

    def test_perimeter_ui_resizes_bars_with_section(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'legacy_single_column.py'),default_timeout=60).run()
        self.assertFalse(app.exception, f'Streamlit crashed: {list(app.exception)}')
        labels=[item.label for item in app.number_input]
        self.assertIn('Bars along x (nx)',labels)
        self.assertIn('Bars along y (ny)',labels)
        self.assertIn('Bar diameter Ø [mm]',labels)
        self.assertIn('Left edge → bar centre [mm]',labels)
        width=next(item for item in app.number_input if item.label=='Width b [mm]')
        width.set_value(400.0).run()
        self.assertFalse(app.exception, f'Streamlit crashed on resizing: {list(app.exception)}')
        self.assertFalse(app.error, f'Streamlit UI error: {list(app.error)}')
        data=app.session_state['draft_input']
        self.assertEqual(data['geometry']['b_m'],.4)
        for variant in data['variants']:
            self.assertEqual(len(variant['bars']),8)
            self.assertAlmostEqual(max(bar['x_m'] for bar in variant['bars']),.35)
            self.assertEqual(variant['reinforcement']['spacing_x_mm'],150)

    def test_cloud_legacy_entrypoint_imports_current_root_backend(self):
        """Exercises the exact file path used by the deployed Streamlit Cloud app."""
        entrypoint = (Path(__file__).resolve().parents[1] /
                      'K18_Streamlit_GitHub_MVP_R0.5' / 'streamlit_app.py')
        app = AppTest.from_file(str(entrypoint), default_timeout=60).run()
        self.assertFalse(app.exception, f'Cloud compatibility path crashed: {list(app.exception)}')
        self.assertFalse(app.error, f'Cloud compatibility path reported an error: {list(app.error)}')
        self.assertTrue(any('Обзор проекта' in x.value for x in app.title))

    def test_cloud_legacy_entrypoint_refreshes_stale_r056_project_model(self):
        """A hot-reloaded Cloud process must not use pre-R0.5.6 model code."""
        import sys
        import multicolumn_r05.project_model as model
        original = model.update_spalling
        delattr(model, "update_spalling")
        try:
            entrypoint = (Path(__file__).resolve().parents[1] /
                          "K18_Streamlit_GitHub_MVP_R0.5" / "streamlit_app.py")
            app = AppTest.from_file(str(entrypoint), default_timeout=60).run()
            self.assertFalse(app.exception, f"Stale R0.5.6 import: {list(app.exception)}")
            self.assertFalse(app.error, f"Stale R0.5.6 UI: {list(app.error)}")
            restored = sys.modules.get("multicolumn_r05.project_model")
            self.assertIsNotNone(restored)
            self.assertTrue(callable(getattr(restored, "update_spalling", None)))
            self.assertTrue(any("Обзор проекта" in x.value for x in app.title))
        finally:
            if not hasattr(model, "update_spalling"):
                model.update_spalling = original

    def test_cloud_sp468_form_replaces_old_manual_only_fields(self):
        """Historical Streamlit Cloud entrypoint opens the new SP468 UI."""
        entrypoint = (Path(__file__).resolve().parents[1] /
                      'K18_Streamlit_GitHub_MVP_R0.5' / 'streamlit_app.py')
        app = AppTest.from_file(str(entrypoint), default_timeout=60).run()
        self.assertFalse(app.exception, f'Cloud entrypoint crashed: {list(app.exception)}')
        page = next(r for r in app.radio if r.label == 'Разделы')
        page.set_value('c1').run()
        self.assertFalse(app.exception, f'Column page crashed: {list(app.exception)}')
        self.assertNotIn('Метод проверки', [r.label for r in app.radio])
        self.assertTrue(any('приложение Л СП 2.02.05-2026' in x.label for x in app.expander))
        self.assertFalse(any('Класс бетона B по СП 468'==x.label for x in app.selectbox))
        self.assertFalse(any('Плотность сухого бетона, кг/м³'==x.label for x in app.text_input))

    def test_cloud_hot_reload_replaces_old_pre_sp468_ui(self):
        """A cached pre-SP468 r056_ui must never survive Cloud hot reload."""
        import sys
        import multicolumn_r05.r056_ui as old_ui
        saved = old_ui.R056_SP468_RELEASE
        delattr(old_ui, 'R056_SP468_RELEASE')
        try:
            entrypoint = (Path(__file__).resolve().parents[1] /
                          'K18_Streamlit_GitHub_MVP_R0.5' / 'streamlit_app.py')
            app = AppTest.from_file(str(entrypoint), default_timeout=60).run()
            self.assertFalse(app.exception, f'Stale SP468 module: {list(app.exception)}')
            loaded = sys.modules.get('multicolumn_r05.r056_ui')
            self.assertIsNotNone(loaded)
            self.assertEqual(getattr(loaded, 'R056_SP468_RELEASE', None),
                             'r056-sp468-20261105-hotfix1')
            page = next(r for r in app.radio if r.label == 'Разделы')
            page.set_value('c1').run()
            self.assertFalse(app.exception)
            self.assertNotIn('Метод проверки', [r.label for r in app.radio])
            self.assertTrue(any('приложение Л СП 2.02.05-2026' in x.label for x in app.expander))
        finally:
            old_ui.R056_SP468_RELEASE = saved

    def test_r062_thermal_editor_and_empty_state_on_historic_cloud_entrypoint(self):
        """The historical Streamlit Cloud URL must expose Annex K controls."""
        entrypoint=(Path(__file__).resolve().parents[1] /
                    "K18_Streamlit_GitHub_MVP_R0.5" / "streamlit_app.py")
        app=AppTest.from_file(str(entrypoint),default_timeout=60).run()
        self.assertFalse(app.exception,f"Cloud startup: {list(app.exception)}")
        page=next(r for r in app.radio if r.label=="Разделы")
        page.set_value("c1").run()
        self.assertFalse(app.exception,f"Column page: {list(app.exception)}")
        self.assertTrue(any("R0.6.2" in x.label for x in app.expander))
        self.assertTrue(any("Сухая плотность" in x.label for x in app.text_input))
        from multicolumn_r05.project_calculator import evaluate_column
        column=app.session_state["project"]["columns"][0]
        self.assertEqual(evaluate_column(column)["thermal_normative"]["status"],"not_evaluated")

    def test_r062_plotted_thermal_field_survives_column_rerun(self):
        """R0.6.2: real data render goes past the new Plotly heatmap path."""
        from multicolumn_r05.project_model import update_thermal_spec
        path=Path(__file__).resolve().parents[1]/"streamlit_app.py"
        app=AppTest.from_file(str(path),default_timeout=60).run()
        self.assertFalse(app.exception)
        model=app.session_state["project"]
        update_thermal_spec(model,"c1",{"concrete_family":"siliceous",
            "dry_density_kg_m3":2400.,
            "exposed_faces":["left","right","bottom","top"]})
        page=next(r for r in app.radio if r.label=="Разделы")
        page.set_value("c1").run()
        self.assertFalse(app.exception, f"Annex K field display: {list(app.exception)}")
        self.assertFalse(app.error, f"Annex K field warning: {list(app.error)}")
        self.assertTrue(any("температурное поле" in t.value.lower() for t in app.subheader))

    def test_r063_mechanics_panel_via_historical_cloud_entrypoint(self):
        """R0.6.3 panel renders with default incomplete inputs and no R90 pass."""
        entrypoint=(Path(__file__).resolve().parents[1] /
                    "K18_Streamlit_GitHub_MVP_R0.5"/"streamlit_app.py")
        app=AppTest.from_file(str(entrypoint),default_timeout=60).run()
        self.assertFalse(app.exception,f"Initial Cloud render: {list(app.exception)}")
        page=next(r for r in app.radio if r.label=="Разделы")
        page.set_value('c1').run()
        self.assertFalse(app.exception,f"Column with R0.6.3: {list(app.exception)}")
        self.assertTrue(any('R0.6.3' in x.label for x in app.expander))
        from multicolumn_r05.project_calculator import evaluate_column
        col=app.session_state["project"]["columns"][0]
        result=evaluate_column(col,grid=20)
        self.assertFalse(result['mechanics_r063']['normative_claim'])

    def test_r063_stress_and_capacity_visualizations_after_loads(self):
        """R0.6.3 interactively executes both new chart branches."""
        from multicolumn_r05.project_model import (update_material_spec,
            update_thermal_spec,update_column,update_section)
        root=Path(__file__).resolve().parents[1]/'streamlit_app.py'
        app=AppTest.from_file(str(root),default_timeout=60).run()
        self.assertFalse(app.exception)
        proj=app.session_state['project']
        update_material_spec(proj,'c1',{'concrete':{
            'aggregate_family':'siliceous','consistency':'S3_S5',
            'curing':'natural','modulus_aggregate':'gravel_granite_upto40',
            'fine_grained':False},'steel':{'product_type':'weldable_bar'}})
        update_thermal_spec(proj,'c1',{'concrete_family':'siliceous',
            'dry_density_kg_m3':2400.,
            'exposed_faces':['left','right','bottom','top']})
        # Positive display fixture stays inside the tabulated material range.
        update_column(proj,'c1',{'fire_minutes':10.})
        update_section(proj,'c1','center',
            {'N_kN':500.,'Mx_kNm':25.,'My_kNm':-20.})
        page=next(r for r in app.radio if r.label=='Разделы')
        page.set_value('c1').run()
        self.assertFalse(app.exception,f'Loaded R0.6.3: {list(app.exception)}')
        stress=next(r for r in app.checkbox if r.key=='r063_stress_c1')
        stress.set_value(True).run()
        self.assertFalse(app.exception,f'Stress map: {list(app.exception)}')
        capacity=next(r for r in app.checkbox if r.key=='r063_capacity_c1')
        capacity.set_value(True).run()
        self.assertFalse(app.exception,f'Capacity envelope: {list(app.exception)}')
        self.assertTrue(any('r063_envelopeplot_c1'==x.key for x in app.get('plotly_chart')))

    def test_cloud_legacy_entrypoint_refreshes_stale_backend(self):
        """Simulate a pre-R0.8 app_core cached during a Streamlit Cloud hot reload."""
        import app_core
        previous = app_core.default_template_bytes
        delattr(app_core, 'default_template_bytes')
        try:
            entrypoint = (Path(__file__).resolve().parents[1] /
                          'K18_Streamlit_GitHub_MVP_R0.5' / 'streamlit_app.py')
            app = AppTest.from_file(str(entrypoint), default_timeout=60).run()
            self.assertFalse(app.exception, f'Stale import recovery failed: {list(app.exception)}')
            self.assertTrue(callable(app_core.default_template_bytes))
        finally:
            if not hasattr(app_core, 'default_template_bytes'):
                app_core.default_template_bytes = previous
