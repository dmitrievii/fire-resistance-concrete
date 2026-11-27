import json
import unittest
from rc_fire.mechanics import sp2026_r9g_hot_domain as g
from rc_fire.mechanics import sp2026_nonisothermal_coupling as b
from rc_fire.mechanics import sp2026_transient_history as tr
from rc_fire.materials.sp2026_fire import concrete_free_thermal_strain_sp

class TestR9G(unittest.TestCase):
 def test_modified_AT_exact_constant_load(self):
    p=tr.Parameters("siliceous",30.,30000.,2.35)
    s=tr.State(stress_MPa=3.)
    inc,w=g.increment(g.MODIFIED_AT,p,s,800.,3.)
    e=concrete_free_thermal_strain_sp(550.,"siliceous",signed_shrinkage=False)
    self.assertAlmostEqual(inc,.1*(2.35*e+.0001*250),places=13)
    self.assertAlmostEqual(w,3*inc,places=13)
 def test_other_integrals(self):
    p=tr.Parameters("siliceous",30.,30000.,2.35);s=tr.State(stress_MPa=3.)
    for mode,expected in ((g.NIELSEN,.1*3.8e-5*780),
        (g.DIEDERICHS,.1*(3.3e-10*780**3-1.72e-7*780**2+4.12e-5*780)),
        (g.ZERO,0.)):
        self.assertAlmostEqual(g.increment(mode,p,s,800.,3.)[0],expected,places=13)
 def test_R9F_parity_and_legacy_domain(self):
    p=b.synthetic();s=g.initial_state(p,g.MODIFIED_AT);a=b.initial_state(p)
    for i,T in enumerate((200.,400.,550.),1):
        a,r=b.trial_step(a,time_s=60*i,temperature_C=T,total_compression=0.)
        s,q=g.trial_step(s,time_s=60*i,temperature_C=T,total_compression=0.)
        self.assertAlmostEqual(r["stress_MPa"],q["stress_MPa"],places=8)
        self.assertAlmostEqual(a.transient_compression,s.active.transient_compression,places=12)
    with self.assertRaises(b.DomainError):
        b.trial_step(a,time_s=240.,temperature_C=551.,total_compression=0.)
 def test_refined_affine_path_and_reheat(self):
    p=tr.Parameters("siliceous",30.,30000.,2.35)
    for mode in g.MODES:
        s=tr.State(stress_MPa=3.)
        a,w=g.increment(mode,p,s,800.,1.)
        x,v=g.increment(mode,p,s,410.,2.)
        m=tr.State(temperature_C=410.,maximum_temperature_C=410.,stress_MPa=2.)
        y,z=g.increment(mode,p,m,800.,1.)
        self.assertAlmostEqual(a,x+y,places=13);self.assertAlmostEqual(w,v+z,places=13)
        m=tr.State(temperature_C=600.,maximum_temperature_C=800.,stress_MPa=1.)
        self.assertEqual(g.increment(mode,p,m,800.,3.),(0.,0.))
 def test_cutoff_exact_800_and_immutable_history(self):
    p=b.synthetic();s=g.initial_state(p,g.MODIFIED_AT)
    for i,T in enumerate((200.,400.,550.,700.,800.),1):
        s,r=g.trial_step(s,time_s=60*i,temperature_C=T,total_compression=0.)
    self.assertFalse(s.thermal_cutoff)
    a,r=g.trial_step(s,time_s=360.,temperature_C=801.,total_compression=.001)
    self.assertTrue(a.thermal_cutoff);self.assertEqual(a.active,s.active)
    self.assertEqual(r["stress_MPa"],0.);self.assertEqual(r["effective_tangent_MPa"],0.)
    c,r=g.trial_step(a,time_s=420.,temperature_C=400.,total_compression=.005)
    self.assertEqual(c.active,a.active);self.assertTrue(c.thermal_cutoff)
    self.assertFalse(s.thermal_cutoff)
 def test_campaign_and_convergence_ledger(self):
    r=g.campaign()
    self.assertEqual(len(r["runs"]),12);self.assertEqual(len(r["comparisons"]),8)
    self.assertTrue(all(x["status"]=="DIAGNOSTIC_COMPLETE" for x in r["runs"]))
    for x in r["runs"]:
        self.assertLess(x["max_compatibility_residual"],1e-11)
        self.assertLess(x["max_energy_residual"],1e-9)
    self.assertEqual(r["cutoff_status"],"DIAGNOSTIC_COMPLETE")
    self.assertTrue(r["cutoff_last"]["thermal_cutoff"])
    self.assertFalse(r["independent_high_temperature_experiment_validated"])
    self.assertIsNone(r["actual_t_R_minutes"])
    print("SP_R9G_EVIDENCE",json.dumps(r,allow_nan=False))
