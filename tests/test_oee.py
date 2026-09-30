import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oee import Totals, load, render, summarize  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data" / "production_log.csv"


def row(planned=480, downtime=60, cycle=2.0, total=12000, good=11400):
    return {"planned_time_min": planned, "downtime_min": downtime, "ideal_cycle_time_s": cycle,
            "total_count": total, "good_count": good}


class TestOEE(unittest.TestCase):
    def test_single_shift_formula(self):
        t = Totals()
        t.add(row())
        self.assertAlmostEqual(t.availability, 420 / 480)
        self.assertAlmostEqual(t.performance, (2.0 * 12000) / (420 * 60))
        self.assertAlmostEqual(t.quality, 11400 / 12000)
        self.assertAlmostEqual(t.oee, t.availability * t.performance * t.quality)

    def test_groups_are_time_weighted(self):
        t = Totals()
        t.add(row(downtime=0))
        t.add(row(downtime=240))
        self.assertAlmostEqual(t.availability, (480 + 240) / 960)

    def test_no_production_does_not_divide_by_zero(self):
        t = Totals()
        t.add(row(downtime=480, total=0, good=0))
        self.assertEqual(t.oee, 0.0)

    def test_sample_data_end_to_end(self):
        s = summarize(load(DATA))
        self.assertEqual(list(s["by_line"]), ["Line 1", "Line 2", "Line 3"])
        self.assertTrue(0 < s["overall"].oee < 1)
        self.assertEqual(s["pareto"][0][0], "Changeover")
        html = render(s, "Test")
        self.assertIn("<svg", html)
        self.assertIn("Line 3", html)


if __name__ == "__main__":
    unittest.main()
