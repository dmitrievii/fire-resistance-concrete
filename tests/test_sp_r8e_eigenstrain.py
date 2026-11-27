"""SP-R8E: analytical invariants and actual self-stress diagnostics."""
import unittest
import json
import copy
import numpy as np
from rc_fire.mechanics.sp2026_eigenstrain_audit import (
    concrete_eigenstrain_components,elastic_compatibility_projection,
    audit_eigenstrain_section,run_eigenstrain_campaign)
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import reference_sp2026_boundary
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from test_sp_r3_member import make_column,user_inputs,make_explicit_spec

def column():
    c=make_column(user_inputs())
    c["fire_minutes"]=45.
    c["thermal_spec"].update(a_red_mode="formula_K1_450C",moisture_mass_pct=1.5)
    return c

class TestEigenstrain(unittest.TestCase):
    def test_components_and_sign(self):
        for family in ("siliceous","calcareous"):
            for t in (20.,100.,300.,500.,700.,800.):
                r=concrete_eigenstrain_components(t,family)
                self.assertAlmostEqual(r["expansion_integral"]+r["signed_shrinkage_integral"],r["total_integral"])
                if t==20.:self.assertEqual(r["total_integral"],0.)
        self.assertIsNone(concrete_eigenstrain_components(801.,"siliceous"))
    def test_compatible_affine_expansion_zero_elastic_stress(self):
        B=np.array([[1.,v,u] for v in (-1.,0.,1.) for u in (-1.,0.,1.)])
        a=np.arange(1.,10.);E=np.linspace(1000.,30000.,9)
        q=np.array([.002,.0004,-.0002])
        r=elastic_compatibility_projection(B,a,E,B@q)
        np.testing.assert_allclose(r["generalized_strain"],-q,atol=1e-14)
        np.testing.assert_allclose(r["mechanical_strain"],0.,atol=1e-14)
        self.assertLess(r["weighted_strain_energy"],1e-20)
    def test_incompatible_expansion_self_equilibrates(self):
        B=np.array([[1.,v,u] for v in (-1.,0.,1.) for u in (-1.,0.,1.)])
        e=.003*(B[:,1]**2+B[:,2]**2)
        r=elastic_compatibility_projection(B,np.ones(9),np.full(9,30000.),e)
        np.testing.assert_allclose(r["generalized_resultant"],0.,atol=1e-10)
        self.assertLess(r["stress"].min(),0.)
        self.assertGreater(r["stress"].max(),0.)
    def test_actual_nonlinear_affine_eigenstrain_invariance(self):
        c=column();p=prepare_sp2026_design_section(c,build_annex_k_snapshot(c,10.),grid=8)
        q=np.array([-.001,.0001,.0002]);a=np.array([.002,-.0003,.0004])
        F,J,m=p.force_and_tangent(q)
        r=copy.deepcopy(p)
        for key,u,v in (("eps_th_c",r.u,r.v),("eps_th_cb",r.bar_u,r.bar_v),
                        ("eps_th_s",r.bar_u,r.bar_v),
                        ("sp_boundary_free_strain",r.sp_boundary_u,r.sp_boundary_v)):
            setattr(r,key,getattr(r,key)+a[0]+a[1]*v+a[2]*u)
        FF,JJ,mm=r.force_and_tangent(q-a)
        np.testing.assert_allclose(F,FF,atol=1e-8)
        np.testing.assert_allclose(J,JJ,atol=1e-6)
        self.assertAlmostEqual(m["critical_mechanical_strain_ratio"],mm["critical_mechanical_strain_ratio"])
    def test_real_free_and_loaded_campaign(self):
        c=column()
        r=run_eigenstrain_campaign(c,make_explicit_spec(c),
            boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
            times_minutes=(5.,10.,30.,45.),heat_grid=64,step_minutes=1.,grid=24,
            effective_creep_phi=0.)
        self.assertEqual(len(r["rows"]),8)
        resolved=0
        for row in r["rows"]:
            ev=row["evidence"]
            if "variants" not in ev:continue
            resolved+=1
            for v in ev["variants"].values():
                for state in (v["free_section"],v["loaded_section"]):
                    if state and "component_reconstruction_max_error" in state:
                        self.assertLess(state["component_reconstruction_max_error"],1e-7)
                        self.assertLess(state["governing_ratio_reconstruction_error"],1e-9)
            zero=ev["variants"]["NO_EIGENSTRAIN_CONTROL"]["free_section"]
            if "critical_ratio" in zero:self.assertLess(zero["critical_ratio"],1e-4)
        self.assertGreater(resolved,0)
        self.assertIsNone(r["actual_t_R_minutes"])
        self.assertFalse(r["normative_claim"])
        print("SP_R8E_EVIDENCE",json.dumps(r,ensure_ascii=True,allow_nan=False))
