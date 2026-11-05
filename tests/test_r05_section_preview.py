"""R0.5 dynamic reinforcement visualization regression tests."""
import unittest

from multicolumn_r05.project_model import new_project, update_column, replace_bars
from multicolumn_r05.section_preview import make_section_figure, section_data


class SectionPreviewTests(unittest.TestCase):
    def test_default_section_shows_eight_true_scale_bars(self):
        column = new_project()["columns"][0]
        data = section_data(column)
        self.assertEqual(len(data["variants"][0]["bars"]), 8)
        self.assertAlmostEqual(data["variants"][0]["bars"][0]["x_m"], 0.04)
        fig = make_section_figure(column)
        circles = [shape for shape in fig.layout.shapes if shape.type == "circle"]
        self.assertEqual(len(circles), 8)
        self.assertAlmostEqual(circles[0].x1-circles[0].x0, 20)
        self.assertIn("600 × 600", fig.layout.title.text)
        self.assertIn("Clear cover", fig.data[0].text[0])

    def test_plot_tracks_overview_geometry_and_bar_changes(self):
        project = new_project()
        update_column(project, "c1", {"b_mm": 720, "bar_diameter_mm": 25})
        column = project["columns"][0]
        fig = make_section_figure(column)
        circles = [s for s in fig.layout.shapes if s.type == "circle"]
        self.assertEqual(len(circles), 8)
        self.assertAlmostEqual(circles[0].x1-circles[0].x0, 25)
        self.assertAlmostEqual(max(s.x1 for s in circles), 690)
        self.assertIn("720 × 600", fig.layout.title.text)
        bars = [dict(x) for x in column["bars"]]
        bars[0]["x_mm"] += 12
        replace_bars(project, "c1", bars)
        changed = make_section_figure(project["columns"][0], show_dimensions=False)
        self.assertAlmostEqual(changed.data[0].x[0], 54.5)
        self.assertEqual(len([s for s in changed.layout.shapes if s.type == "circle"]), 8)

    def test_temperature_is_shown_only_for_computed_section(self):
        column = new_project()["columns"][0]
        without = make_section_figure(column)
        self.assertNotIn("Temperature", without.data[0].text[0])
        result = {"results": {"bottom": {
            "bars": [{"id": b["id"], "temperature_C": 430.0}
                     for b in column["bars"]]
        }}}
        with_result = make_section_figure(column, result)
        self.assertIn("430", with_result.data[0].text[0])


if __name__ == "__main__":
    unittest.main()
