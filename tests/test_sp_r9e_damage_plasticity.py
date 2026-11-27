import json
import unittest
from rc_fire.mechanics.sp2026_damage_plasticity import (
    initial_state,trial_step,run_history,benchmark_parameters,benchmark_campaign,
    identify_unloading,monotonic_nonidentifiability,DomainError)

class TestR9E(unittest.TestCase):
    def setUp(self):self.p=benchmark_parameters(400.,50.)
    def trial(self,s,e):return trial_step(s,mechanical_compression=e,temperature_C=self.p.temperature_C)
    def test_peak_and_postpeak_exact(self):
        p=self.p;s=initial_state(p)
        a,r=self.trial(s,p.peak_strain)
        self.assertAlmostEqual(r["stress_MPa"],p.peak_stress_MPa)
        self.assertAlmostEqual(r["plastic_strain"],p.p_peak)
        b,r=self.trial(a,p.peak_strain+.5*p.p_soft)
        self.assertAlmostEqual(r["damage"],.5)
        self.assertAlmostEqual(r["stress_MPa"],.5*p.peak_stress_MPa)
        c,r=self.trial(b,p.end_strain)
        self.assertEqual(r["damage"],1.)
        self.assertEqual(r["stress_MPa"],0.)
    def test_unloading_reloading_and_crushing_memory(self):
        p=self.p;half=p.peak_strain+.5*p.p_soft
        h=run_history(p,[half,p.p_peak+.5*p.p_soft,half,p.end_strain,0.,half])["rows"]
        self.assertAlmostEqual(h[0]["unloading_modulus_MPa"],.5*p.elastic_modulus_MPa)
        self.assertAlmostEqual(h[1]["stress_MPa"],0.)
        self.assertAlmostEqual(h[2]["stress_MPa"],h[0]["stress_MPa"])
        self.assertEqual(h[1]["plastic_strain"],h[0]["plastic_strain"])
        self.assertEqual(h[2]["delta_plastic_dissipation_MPa"],0.)
        self.assertEqual(h[2]["delta_damage_dissipation_MPa"],0.)
        self.assertEqual(h[-1]["damage"],1.)
        self.assertEqual(h[-1]["stress_MPa"],0.)
    def test_consistent_tangent_away_from_kinks(self):
        p=self.p;s=initial_state(p)
        for e in ((p.fy/p.elastic_modulus_MPa+p.peak_strain)/2,
                  p.peak_strain+.5*p.p_soft):
            a,r=self.trial(s,e);h=1e-8
            _,lo=self.trial(s,e-h);_,hi=self.trial(s,e+h)
            self.assertAlmostEqual((hi["stress_MPa"]-lo["stress_MPa"])/(2*h),
                                   r["algorithmic_tangent_MPa"],delta=1e-4)
        a,r=self.trial(s,p.peak_strain+.5*p.p_soft)
        e=a.mechanical_compression-.2*p.peak_stress_MPa/p.elastic_modulus_MPa
        _,r=self.trial(a,e);_,lo=self.trial(a,e-1e-8);_,hi=self.trial(a,e+1e-8)
        self.assertAlmostEqual((hi["stress_MPa"]-lo["stress_MPa"])/2e-8,
                               r["algorithmic_tangent_MPa"],delta=1e-4)
    def test_regularization_energy_and_subdivision(self):
        r=benchmark_campaign()
        for row in r["regularization"]:
            self.assertAlmostEqual(row["postpeak_external_work_N_mm"],5.,places=10)
            self.assertAlmostEqual(row["ledger_postpeak_work_N_mm"],5.,places=10)
            self.assertAlmostEqual(row["postpeak_total_dissipation_N_mm"],
                 5.+row["released_peak_elastic_energy_N_mm"],places=10)
        p=self.p
        a,ra=self.trial(initial_state(p),p.end_strain)
        b=initial_state(p)
        work=0.
        for i in range(1,101):
            b,rb=self.trial(b,p.end_strain*i/100)
            work+=rb["delta_external_work_exact_MPa"]
        self.assertAlmostEqual(a.plastic_compression,b.plastic_compression)
        self.assertAlmostEqual(work,ra["delta_external_work_exact_MPa"],places=12)
        # independent piecewise trapezoidal work check through a cyclic history
        h=run_history(p,[0.,p.fy/p.elastic_modulus_MPa,p.peak_strain,
            p.peak_strain+.5*p.p_soft,p.p_peak+.5*p.p_soft,
            p.peak_strain+.5*p.p_soft,p.end_strain])["rows"]
        for x,y in zip(h,h[1:]):
            w=.5*(x["stress_MPa"]+y["stress_MPa"])*(y["strain"]-x["strain"])
            self.assertAlmostEqual(w,y["delta_external_work_exact_MPa"],places=12)
        print("SP_R9E_EVIDENCE",json.dumps(r,allow_nan=False))
    def test_inverse_unloading_and_nonidentifiability(self):
        p=self.p;s,r=self.trial(initial_state(p),p.peak_strain+.5*p.p_soft)
        e2=r["strain"]-.2*p.peak_stress_MPa/p.elastic_modulus_MPa
        _,r2=self.trial(s,e2)
        i=identify_unloading(elastic_modulus_MPa=p.elastic_modulus_MPa,
            peak_of_unload_strain=r["strain"],peak_of_unload_stress_MPa=r["stress_MPa"],
            second_strain=e2,second_stress_MPa=r2["stress_MPa"])
        self.assertAlmostEqual(i["damage"],r["damage"])
        self.assertAlmostEqual(i["plastic_strain"],r["plastic_strain"])
        a=monotonic_nonidentifiability(elastic_modulus_MPa=p.elastic_modulus_MPa,
            strain=r["strain"],stress_MPa=r["stress_MPa"])
        self.assertGreater(a["damage_interval"][1],r["damage"])
        self.assertFalse(a["unique_damage_plasticity_identification"])
    def test_trial_and_domain(self):
        s=initial_state(self.p)
        a,_=self.trial(s,self.p.peak_strain)
        self.assertEqual(s.plastic_compression,0.)
        self.assertGreater(a.plastic_compression,0.)
        with self.assertRaises(DomainError):
            trial_step(a,mechanical_compression=.004,temperature_C=500.)
