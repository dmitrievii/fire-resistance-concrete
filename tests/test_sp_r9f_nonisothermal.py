import json
import unittest
from rc_fire.mechanics.sp2026_nonisothermal_coupling import (
    initial_state,trial_step,run_path,synthetic,campaign,DomainError)
from rc_fire.mechanics.sp2026_damage_plasticity import benchmark_parameters,run_history
from rc_fire.mechanics.sp2026_transient_history import concrete_free_thermal_strain_sp

class TestR9F(unittest.TestCase):
 def test_isothermal_reduction_to_R9E(self):
    p=synthetic(0.)
    b=benchmark_parameters(20.,50.)
    es=[0.,b.peak_strain,b.peak_strain+.5*b.p_soft,b.p_peak+.5*b.p_soft,
        b.peak_strain+.5*b.p_soft,b.end_strain,0.,b.peak_strain]
    ref=run_history(b,es)["rows"]
    s=initial_state(p)
    for i,(e,r) in enumerate(zip(es,ref),1):
        s,x=trial_step(s,time_s=i,temperature_C=20.,total_compression=e)
        self.assertAlmostEqual(x["stress_MPa"],r["stress_MPa"],places=8)
        self.assertAlmostEqual(s.plastic_compression,r["plastic_strain"],places=12)
        self.assertAlmostEqual(s.damage,r["damage"],places=10)
 def test_thermal_transfer_does_not_heal(self):
    p=synthetic(0.);s=initial_state(p)
    s,r=trial_step(s,time_s=1.,temperature_C=20.,total_compression=.02)
    self.assertEqual(s.damage,1.)
    z=s.plastic_compression
    for i,T in enumerate((400.,200.,400.,500.),2):
        s,r=trial_step(s,time_s=i,temperature_C=T,total_compression=.001)
        self.assertEqual(s.damage,1.)
        self.assertEqual(s.plastic_compression,z)
        self.assertEqual(s.stress_MPa,0.)
 def test_creep_dwell_and_reheating(self):
    s=initial_state(synthetic(2.35,1e8))
    s,r=trial_step(s,time_s=60.,temperature_C=200.,total_compression=0.)
    tr=s.transient_compression;cr=s.basic_creep_compression;sig=s.stress_MPa
    a,x=trial_step(s,time_s=660.,temperature_C=200.,total_compression=0.)
    self.assertEqual(a.transient_compression,tr)
    self.assertGreater(a.basic_creep_compression,cr)
    self.assertLess(a.stress_MPa,sig)
    b,_=trial_step(a,time_s=720.,temperature_C=100.,total_compression=0.)
    c,_=trial_step(b,time_s=780.,temperature_C=200.,total_compression=0.)
    self.assertEqual(c.transient_compression,tr)
 def test_free_thermal_path(self):
    s=initial_state(synthetic())
    e=-concrete_free_thermal_strain_sp(400.,"siliceous")
    a,r=trial_step(s,time_s=100.,temperature_C=400.,total_compression=e)
    self.assertAlmostEqual(a.stress_MPa,0.,places=8)
    self.assertAlmostEqual(a.transient_compression,0.,places=12)
    self.assertEqual(a.damage,0.)
 def test_tangent_and_rejected_trial(self):
    s=initial_state(synthetic())
    kw=dict(time_s=60.,temperature_C=200.)
    _,r=trial_step(s,**kw,total_compression=.0001)
    _,a=trial_step(s,**kw,total_compression=.0001-1e-8)
    _,b=trial_step(s,**kw,total_compression=.0001+1e-8)
    self.assertAlmostEqual((b["stress_MPa"]-a["stress_MPa"])/2e-8,
                           r["effective_tangent_MPa"],delta=.02)
    self.assertEqual(s.time_s,0.)
    with self.assertRaises(DomainError):
        trial_step(s,time_s=60.,temperature_C=551.,total_compression=0.)
    p=synthetic(2.35,1e3)
    with self.assertRaises(DomainError):
        trial_step(initial_state(p),time_s=1000.,temperature_C=400.,total_compression=0.)
 def test_real_coupling_campaign(self):
    r=campaign()
    self.assertEqual(len(r["runs"]),9)
    self.assertTrue(all(x["status"]=="DIAGNOSTIC_COMPLETE" for x in r["runs"]))
    for x in r["runs"]:
        self.assertLess(x["max_compatibility_residual"],1e-11)
        self.assertLess(x["max_split_energy_residual"],1e-9)
    self.assertFalse(r["full_thermodynamic_qualification"])
    self.assertIsNone(r["actual_t_R_minutes"])
    print("SP_R9F_EVIDENCE",json.dumps(r,allow_nan=False))
