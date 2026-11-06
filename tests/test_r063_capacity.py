"""Experimental directional capacity surface: numerical, non-certifying tests."""
import unittest

from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.mechanics import prepare_section, approximate_biaxial_capacity
from test_r063_mechanics import sample_column


class DirectionalCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c=sample_column()
        cls.section=prepare_section(c,evaluate_rectangular_column(c,grid=18),grid=18)

    def test_biaxial_moment_capacity_and_warning(self):
        c=approximate_biaxial_capacity(self.section,500,25,-20,angular_samples=32)
        self.assertEqual(c['status'],'approximate_capacity_diagnostic')
        self.assertFalse(c['normative_claim'])
        self.assertGreater(c['capacity_directional_kNm'],20)
        self.assertLess(c['utilization_diagnostic'],1)
        self.assertIn('НЕ ПОДТВЕРЖДЕНА',c['warning'])

    def test_moment_scaling_is_linear_for_fixed_N_and_direction(self):
        a=approximate_biaxial_capacity(self.section,500,25,-20,angular_samples=24)
        b=approximate_biaxial_capacity(self.section,500,50,-40,angular_samples=24)
        self.assertAlmostEqual(a['capacity_directional_kNm'],b['capacity_directional_kNm'],places=5)
        self.assertAlmostEqual(b['utilization_diagnostic'],2*a['utilization_diagnostic'],places=5)

    def test_reversal_symmetric_rebar_envelope(self):
        a=approximate_biaxial_capacity(self.section,500,20,12,angular_samples=32)
        b=approximate_biaxial_capacity(self.section,500,-20,-12,angular_samples=32)
        self.assertAlmostEqual(a['capacity_directional_kNm'],b['capacity_directional_kNm'],delta=3)

    def test_grid_angular_approximation_converges(self):
        a=approximate_biaxial_capacity(self.section,500,40,10,angular_samples=24)
        b=approximate_biaxial_capacity(self.section,500,40,10,angular_samples=48)
        self.assertLess(abs(a['capacity_directional_kNm']-b['capacity_directional_kNm'])/
                        b['capacity_directional_kNm'],.05)

    def test_invalid_axial_force_rejected_without_claim(self):
        c=approximate_biaxial_capacity(self.section,90000,20,10,angular_samples=24)
        self.assertEqual(c['status'],'axial_force_outside_supported_strain_domain')
        self.assertFalse(c['normative_claim'])

if __name__=='__main__':unittest.main()