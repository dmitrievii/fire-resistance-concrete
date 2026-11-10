"""Reintroduce physical cross-section heatmap without resurrecting SP Annex K.

Source must be the same time-stamped TKP 2D FVM field used for material
reduction, not a synthetic heat illustration or the archived SP K model.
"""
import unittest
import numpy as np

from test_r07_public_workflow import user_inputs
from rc_fire.integration.r07_inputs import make_column
from rc_fire.integration.r07_public import fire_assessment
from rc_fire.thermal.tkp_section_plot import make_tkp_section_heatmap


class PublicHeatingSectionPlot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=make_column(user_inputs())
        cls.r=fire_assessment(cls.c,required_minutes=30.,
            steel_route="hot_rolled",ductility_class="B",
            moisture_mass_pct=1.5,grid=8,dt_minutes=3.)

    def test_raw_field_is_same_solved_FVM_snapshot_as_thermal_time_series(self):
        r=self.r
        self.assertEqual(r["thermal_grid"]["nx"],8)
        self.assertEqual(r["thermal_grid"]["ny"],8)
        frames=r["thermal_timeline"]
        self.assertTrue(all("grid_temperature_C" in row for row in frames))
        self.assertTrue(all("surface_temperature_C" in row for row in frames))
        self.assertEqual(frames[0]["minute"],0.)
        self.assertTrue(np.allclose(frames[0]["grid_temperature_C"],20.))
        for row in frames:
            arr=np.asarray(row["grid_temperature_C"])
            self.assertEqual(arr.shape,(8,8))
            self.assertTrue(np.all(np.isfinite(arr)))
            self.assertGreaterEqual(np.min(arr),20.-1e-6)
            self.assertLessEqual(np.max(arr),row["gas_C"]+1e-5)
            self.assertEqual(len(row["bars_C"]),8)

    def test_heatmap_uses_exact_same_cell_grid_and_all_actual_steel_positions(self):
        r=self.r
        frame=next(row for row in r["thermal_timeline"] if row["minute"]==30.)
        fig=make_tkp_section_heatmap(self.c,frame,r["thermal_grid"],
            color_max_C=1000.)
        self.assertTrue(np.array_equal(
            np.asarray(fig.data[0].z),np.asarray(frame["grid_temperature_C"])))
        self.assertEqual(fig.layout.meta["temperature_method"],"TKP_4.3.2_FVM")
        self.assertEqual(fig.layout.meta["time_minutes"],30.)
        traces=[x for x in fig.data if x.type=="scatter"]
        self.assertEqual(len(traces),1)
        points=traces[0]
        self.assertEqual(len(points.x),8)
        self.assertEqual(set(points.text),set(b["id"] for b in self.c["bars"]))
        self.assertEqual(points.x[0],40.)
        self.assertEqual(points.y[0],40.)
        self.assertIn("S1:",str(points.customdata[0]))
        self.assertIn("°C",str(points.customdata[0]))
        self.assertEqual(len([shape for shape in fig.layout.shapes
                              if shape.type=="circle"]),8)

    def test_no_made_up_heatmap_for_old_public_result_without_2D_cells(self):
        row=dict(self.r["thermal_timeline"][-1])
        row.pop("grid_temperature_C")
        with self.assertRaises(ValueError):
            make_tkp_section_heatmap(self.c,row,self.r["thermal_grid"])

    def test_out_of_domain_field_cannot_be_displayed_as_tkp_solution(self):
        row=dict(self.r["thermal_timeline"][-1])
        row["grid_temperature_C"]=[[2000.]*8 for _ in range(8)]
        with self.assertRaises(ValueError):
            make_tkp_section_heatmap(self.c,row,self.r["thermal_grid"])

    def test_initial_time_has_true_initial_cells_and_steel_no_false_isotherm(self):
        r=self.r;row=r["thermal_timeline"][0]
        fig=make_tkp_section_heatmap(self.c,row,r["thermal_grid"])
        self.assertEqual(fig.layout.meta["time_minutes"],0.)
        self.assertFalse(any(x.type=="contour" for x in fig.data))
        self.assertEqual([x for x in fig.data if x.type=="scatter"][0].text[0],
                         self.c["bars"][0]["id"])


if __name__=="__main__":
    unittest.main()
