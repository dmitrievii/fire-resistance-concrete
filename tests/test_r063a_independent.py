"""R0.6.3A independent invariants; uses closed-form answers rather than same solver."""
import copy, math, unittest
import numpy as np
from rc_fire.mechanics import prepare_section, solve_load, SectionMechanicsError
from rc_fire.thermal import evaluate_rectangular_column
from test_r063_mechanics import sample_column

class IndependentQualification(unittest.TestCase):
    def section(self, minutes=0, grid=24):
        c=sample_column(); c['fire_minutes']=minutes
        return prepare_section(c,evaluate_rectangular_column(c,grid=20),grid=grid)

    def test_uniform_strain_closed_form_three_levels(self):
        p=self.section()
        steel_area=8*math.pi*.01**2
        for eps in (.00025,.001,.002,.003):
            conc=25*(1-(1-min(1,eps/.002))**2)
            steel=min(500.,200000*eps)
            expected=1000*(conc*(.36-steel_area)+steel*steel_area)
            with self.subTest(eps=eps):
                f,_,_=p.response([eps,0,0])
                self.assertAlmostEqual(float(f[0]),expected,places=7)
                self.assertAlmostEqual(float(f[1]),0,places=7)
                self.assertAlmostEqual(float(f[2]),0,places=7)

    def test_corner_strain_limit_independent_of_grid(self):
        u=np.array([.00015,.00172,.00172]); actual=float(u[0]+abs(u[1])+abs(u[2]))
        self.assertGreater(actual,.0035)
        for grid in (12,20,40):
            with self.subTest(grid=grid):
                p=self.section(grid=grid)
                _,_,m=p.response(u)
                self.assertAlmostEqual(m['max_concrete_compression'],actual,places=12)
                self.assertGreater(m['max_concrete_compression'],p.eps_cu2)

    def test_temperature_table_guard_is_grid_independent(self):
        for grid in (12,16,32,64,96):
            with self.subTest(grid=grid):
                with self.assertRaisesRegex(SectionMechanicsError,'800'):
                    self.section(minutes=30,grid=grid)

    def test_valid_thermal_field_refinement(self):
        force=[]
        for grid in (16,32,64,96):
            p=self.section(minutes=10,grid=grid)
            f,_,_=p.response([.0008,.00035,-.0002]);force.append(f)
            r=solve_load(p,500,25,-20)
            self.assertTrue(r['equilibrium'])
            self.assertFalse(r['normative_claim'])
        f=np.asarray(force)
        relative=np.abs((f[-2]-f[-1])/np.maximum(np.abs(f[-1]),1.))
        self.assertTrue(np.all(relative<.012),f'{relative}')

    def test_section_axis_permutation(self):
        p=self.section(grid=32)
        a=p.response([.0008,.00015,-.00027])[0]
        b=p.response([.0008,-.00027,.00015])[0]
        np.testing.assert_allclose(a,[b[0],b[2],b[1]],atol=1e-8)

if __name__=='__main__':unittest.main()
