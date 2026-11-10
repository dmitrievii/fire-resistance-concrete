"""SP-R.2 normative-source thermal physics and coupling regressions.

This campaign confirms implementation consistency. The SP §8.2.23
convection/emissivity inputs and effective moisture model still require
project evidence; the historical 400mm SP Annex Zh matrix has incomplete
boundary provenance and is used for independent diagnostic comparison.
No numerical test implies qualification of a whole-column R(t).
"""
from __future__ import annotations

import copy
import math
import unittest

import numpy as np

from test_r07_public_workflow import user_inputs
from rc_fire.integration.r07_inputs import make_column
from rc_fire.integration.r07_public import fire_assessment
from rc_fire.thermal.sp2026_heat import (
    SPHeatError,SP_K1,
    sp_conductivity,sp_specific_heat,sp_nominal_diffusivity,
    _vol_enthalpy,_vol_heat_capacity,
    reference_sp2026_boundary,solve_sp2026_2d_heat,
    select_sp2026_snapshot,sample_sp2026_temperature,
    standard_fire_sp)
from rc_fire.thermal.sp2026_verification import (
    compare_sp2026_thermal_refinement,appendix_zh7_comparison,ZH7)
from rc_fire.mechanics.sp2026_section import prepare_sp2026_section
from rc_fire.thermal.tkp_section_plot import make_tkp_section_heatmap


class SPAppendixK1ExactMaterialTests(unittest.TestCase):
    def test_table_K1_siliceous_and_calcareous_A_B_D_E_are_exact(self):
        self.assertEqual(SP_K1["siliceous"],
                         (1.20,-.00035,.71,.00083,2.5))
        self.assertEqual(SP_K1["calcareous"],
                         (1.14,-.00055,.71,.00083,3.0))
        self.assertAlmostEqual(sp_conductivity(
            450.,aggregate="siliceous"),1.0425)
        self.assertAlmostEqual(sp_conductivity(
            500.,aggregate="calcareous"),.865)
        self.assertAlmostEqual(sp_specific_heat(
            450.,aggregate="siliceous",moisture_mass_pct=2.5),1208.5)
        self.assertAlmostEqual(sp_specific_heat(
            450.,aggregate="calcareous",moisture_mass_pct=3.),1233.5)

    def test_formula_K1_effective_diffusivity_exact_units(self):
        sp=sp_nominal_diffusivity(
            450.,aggregate="siliceous",rho_dry_kg_m3=2200.,
            moisture_mass_pct=2.5)
        expected=3.6*1.0425/(2200.*(1.0835+.125))
        self.assertAlmostEqual(sp,expected,places=13)
        self.assertGreater(sp,0.)

    def test_enthalpy_derivative_is_actual_SP_effective_volumetric_capacity(self):
        for aggregate in ("siliceous","calcareous"):
            for T in (20.,100.,450.,900.,1100.):
                dT=.001
                h_plus=float(_vol_enthalpy(
                    np.asarray([T+dT]),2200.,aggregate,1.5)[0])
                h_minus=float(_vol_enthalpy(
                    np.asarray([T-dT if T-dT>=20 else 20.]),
                    2200.,aggregate,1.5)[0])
                derivative=(h_plus-h_minus)/(2*dT if T>20. else dT)
                cp=float(_vol_heat_capacity(
                    np.asarray([T]),2200.,aggregate,1.5)[0])
                self.assertAlmostEqual(derivative/cp,1.,places=6)

    def test_wet_concrete_has_greater_effective_capacity(self):
        dry=sp_specific_heat(500.,aggregate="siliceous",
                             moisture_mass_pct=0.)
        wet=sp_specific_heat(500.,aggregate="siliceous",
                             moisture_mass_pct=3.)
        self.assertAlmostEqual(wet-dry,150.)
        self.assertEqual(standard_fire_sp(0.),20.)
        self.assertAlmostEqual(standard_fire_sp(90.),
                 20.+345.*math.log10(721.),places=10)

    def test_sp2026_never_silently_uses_tkp_thermal_properties(self):
        from rc_fire.materials.tkp_en1992_fire import (
            concrete_thermal_conductivity,concrete_specific_heat)
        self.assertNotAlmostEqual(
            sp_conductivity(500.,aggregate="siliceous"),
            concrete_thermal_conductivity(500.),places=5)
        self.assertNotAlmostEqual(
            sp_specific_heat(500.,aggregate="siliceous",
                             moisture_mass_pct=1.5),
            concrete_specific_heat(500.,mass_moisture_pct=1.5),places=4)

    def test_source_boundaries_and_range_requirements_fail_closed(self):
        with self.assertRaises(SPHeatError):
            sp_conductivity(1300.,aggregate="siliceous")
        with self.assertRaises(SPHeatError):
            sp_conductivity(100.,aggregate="lightweight")
        with self.assertRaises(SPHeatError):
            sp_specific_heat(20.,aggregate="siliceous",
                             moisture_mass_pct=-1.)
        b=reference_sp2026_boundary(moisture_mass_pct=1.5)
        self.assertIn("ТКП",b["environment_source"])
        self.assertEqual(b["fire_curve"],"sp2026_standard_formula_3")
        self.assertEqual(b["convection_W_m2_K"],25.)


class SP2026TransientHeat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.column["fire_minutes"]=30.
        cls.boundary=reference_sp2026_boundary(moisture_mass_pct=1.5)
        cls.heat=solve_sp2026_2d_heat(
            cls.column,boundary=cls.boundary,
            cell_count_x=8,cell_count_y=8,max_step_minutes=3.,
            sample_times_minutes=[5.,15.,30.])

    def test_source_and_energy_balance(self):
        x=self.heat
        self.assertEqual(x["thermal_method"],"SP2026_8.2.23_FVM")
        self.assertIn("таблица К.1",x["governing_source"])
        self.assertEqual(x["status"],"evaluated_sp2026_thermal_diagnostic")
        self.assertTrue(x["source_transport_laws_independent_of_TKP"])
        self.assertFalse(x["external_boundary_normative_qualified"])
        self.assertFalse(x["normative_claim"])
        self.assertIsNone(x["R_t_minutes"])
        self.assertLess(x["energy_balance"]["relative_cumulative_residual"],3e-4)
        self.assertLess(x["energy_balance"]["worst_step_relative_residual"],3e-4)
        self.assertEqual([s["time_minutes"] for s in x["snapshots"]],
                         [5.,15.,30.])

    def test_four_sided_symmetry_and_physical_temperature_order(self):
        x=self.heat
        snap=select_sp2026_snapshot(x,30.)
        T=np.asarray(snap["snapshot"]["grid_temperature_C"])
        self.assertEqual(T.shape,(8,8))
        self.assertTrue(np.allclose(T,T[::-1,:],atol=.001))
        self.assertTrue(np.allclose(T,T[:,::-1],atol=.001))
        self.assertGreater(T[0,0],T[3,3])
        self.assertGreater(T[0,0],20.)
        self.assertLess(np.max(T),standard_fire_sp(30.))
        self.assertAlmostEqual(
            sample_sp2026_temperature(snap,300.,300.),
            sample_sp2026_temperature(snap,300.,300.))

    def test_rebar_positions_and_temperature_mechanics_are_identical(self):
        src=select_sp2026_snapshot(self.heat,30.)
        p=prepare_sp2026_section(self.column,src,grid=8)
        self.assertEqual(len(p.bar_ids),8)
        self.assertIn("SP2026_8.2.23_K1_FVM",p.source["thermal"])
        self.assertTrue(np.all(p.theta_s<800.))
        self.assertEqual(len(p.theta_c),64)
        self.assertTrue(np.all(np.isfinite(p.eps_th_c)))
        for i,bar in enumerate(self.column["bars"]):
            self.assertAlmostEqual(
                p.theta_s[i],
                sample_sp2026_temperature(
                    src,bar["x_mm"],bar["y_mm"]),places=10)
        F,J,meta=p.force_and_tangent(
            np.array([-.001,0.,0.]),include_maps=True)
        self.assertTrue(np.all(np.isfinite(F)))
        self.assertTrue(np.all(np.isfinite(J)))
        self.assertFalse(meta["normative_claim"])

    def test_sp_surface_is_from_implicit_conductive_radiative_flux(self):
        snap=self.heat["snapshots"][-1]
        surf=snap["surface_temperature_C"]
        self.assertEqual(len(surf["left"]),8)
        self.assertLess(snap["boundary_max_C"],standard_fire_sp(30.))
        self.assertGreater(snap["boundary_max_C"],20.)
        self.assertTrue(all(float(x)>=20 for face in surf.values() for x in face))

    def test_sp_section_plot_has_white_background_and_correct_source(self):
        source=select_sp2026_snapshot(self.heat,30.)
        g=self.heat["grid"];snap=source["snapshot"]
        frame={
            "temperature_source":"SP2026 2D FVM solved snapshot",
            "minute":30.,"gas_C":standard_fire_sp(30.),
            "grid_temperature_C":snap["grid_temperature_C"],
            "bars_C":{
                str(bar["id"]):sample_sp2026_temperature(
                    source,bar["x_mm"],bar["y_mm"])
                for bar in self.column["bars"]}}
        fig=make_tkp_section_heatmap(self.column,frame,g)
        self.assertEqual(fig.layout.meta["temperature_method"],
                         "SP2026_8.2.23_FVM")
        self.assertEqual(fig.layout.plot_bgcolor,"white")
        self.assertEqual(fig.layout.paper_bgcolor,"white")

    def test_adiabatic_sides_without_fire_remain_at_ambient(self):
        c=copy.deepcopy(self.column)
        c["thermal_spec"]["exposed_faces"]=[]
        h=solve_sp2026_2d_heat(c,boundary=self.boundary,
            cell_count_x=4,cell_count_y=4,max_step_minutes=3.,
            sample_times_minutes=[30.])
        self.assertTrue(np.allclose(h["snapshots"][-1]["grid_temperature_C"],
                                    20.,atol=1e-6))
        self.assertAlmostEqual(h["energy_balance"]["integrated_boundary_heat_J_per_m"],
                               0.,delta=.00001)


class SP2026RefinementAndNormativeReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.boundary=reference_sp2026_boundary(moisture_mass_pct=1.5)

    def test_three_mesh_two_timestep_campaign_is_real_and_not_certification(self):
        r=compare_sp2026_thermal_refinement(
            self.column,boundary=self.boundary,
            sample_time_minutes=20.,grids=(8,12,16),
            time_steps=(3.,1.5))
        self.assertEqual(len(r["models"]),4)
        self.assertEqual([x["grid"] for x in r["models"]],
                         [8,12,16,16])
        self.assertEqual([x["time_step_minutes"] for x in r["models"]],
                         [3.,3.,3.,1.5])
        self.assertEqual(len(r["fine_temporal_refinement"][
            "bar_temperature_differences_C"]),8)
        self.assertGreaterEqual(r["intermediate_to_fine"][
            "max_bar_delta_abs_C"],0.)
        self.assertTrue(all(x["energy_residual"]<3e-4
                            for x in r["models"]))
        self.assertFalse(r["sp2026_823_model_fully_qualified"])
        self.assertFalse(r["normative_claim"])

    def test_independent_SP_Zh7_reference_is_compared_without_calibration(self):
        c=make_column(user_inputs())
        c["b_mm"]=400.
        c["h_mm"]=400.
        c["fire_minutes"]=90.
        # This Appendix Ж benchmark uses an independent *concrete*
        # temperature field; bar locations don't enter this comparison.
        model=solve_sp2026_2d_heat(c,boundary=self.boundary,
            cell_count_x=12,cell_count_y=12,
            max_step_minutes=5.,sample_times_minutes=[90.])
        result=appendix_zh7_comparison(model)
        self.assertEqual(len(result["pointwise"]),len(ZH7))
        self.assertGreater(result["RMSE_C"],0.)
        self.assertFalse(result["automatic_calibration_performed"])
        self.assertFalse(result["source_boundary_comparability_qualified"])
        self.assertFalse(result["normative_claim"])
        self.assertEqual(result["reference"],
                         "СП 2.02.05-2026, приложение Ж, таблица Ж.7")


class PublicSP2026ThermalDefault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.column=make_column(user_inputs())
        cls.r=fire_assessment(cls.column,required_minutes=30.,
            steel_route="hot_rolled",ductility_class="B",
            moisture_mass_pct=1.5,grid=8,dt_minutes=3.)

    def test_sp_is_separate_solution_not_renamed_tkp(self):
        r=self.r
        self.assertEqual(r["sp2026_stage2_heat_status"],
            "SP2026_K1_FVM_EVALUATED_WITH_UNQUALIFIED_BOUNDARY")
        self.assertEqual(r["sp2026_stage2_thermal_grid"]["nx"],8)
        self.assertEqual(r["sp2026_stage2_heat_horizon_minutes"],60.)
        self.assertEqual(r["sp2026_stage2_thermal_timeline"][0]["minute"],0.)
        self.assertEqual(r["sp2026_stage2_thermal_timeline"][-1]["minute"],60.)
        self.assertEqual(r["sp2026_stage2_thermal_timeline"][0]["bars_C"][
            "S1"],20.)
        self.assertLess(r["sp2026_stage2_heat_energy_balance"][
            "relative_cumulative_residual"],3e-4)
        self.assertIn("СП",r["sp2026_stage2_thermal_source"])
        self.assertIn("ТКП",r["sp2026_stage2_boundary_source"])
        # Critical: SP material and SP thermal must be coupled from SAME
        # source, not SP mechanics with hidden TKP temperatures.
        self.assertEqual(r["sp2026_stage1_at_required_time"][
            "temperature_method"],"SP2026_8.2.23_FVM")
        self.assertNotEqual(
            r["sp2026_stage2_thermal_timeline"][-1]["temperature_source"],
            r["thermal_timeline"][-1]["temperature_source"])
        self.assertIsNone(r["R_t_minutes"])
        self.assertEqual(r["regulatory_result"],"NOT_ESTABLISHED")


if __name__=="__main__":
    unittest.main()
