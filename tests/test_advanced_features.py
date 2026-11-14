import unittest
from datetime import datetime, time, timedelta

from core.constraints import check_horizon_limit, check_max_continuous_run
from core.params import SKU, ProductionLine, ProductionParams, Shift
from core.solution import LineSolution, ProductionBlock, ScheduleSolution
from optimizer.genetic import GeneticOptimizer


class TestAdvancedFeatures(unittest.TestCase):

    def setUp(self):
        self.start = datetime(2025, 1, 1, 8, 0)
        self.sku = SKU("A", "Test", 100)
        self.line = ProductionLine("L1", "Line", ["A"], 10.0)

    def test_horizon_constraint(self):
        # 1 day horizon
        params = ProductionParams(
            lines=[self.line], skus=[self.sku], shifts=[],
            start_date=self.start, planning_horizon_days=1.0
        )

        # Block ending at T+25h (Outside horizon)
        block = ProductionBlock("B1", "L1", "A",
                                self.start + timedelta(hours=24),
                                self.start + timedelta(hours=25),
                                10)
        ls = LineSolution("L1", [block])
        sol = ScheduleSolution([ls], params)

        violations = check_horizon_limit(sol)
        self.assertEqual(len(violations), 1)
        self.assertIn("outside planning horizon", violations[0].message)

        # Block ending at T+23h (Inside)
        block2 = ProductionBlock("B2", "L1", "A",
                                 self.start + timedelta(hours=22),
                                 self.start + timedelta(hours=23),
                                 10)
        ls.production_blocks = [block2]
        violations = check_horizon_limit(sol)
        self.assertEqual(len(violations), 0)

    def test_max_continuous_run_constraint(self):
        self.line.max_continuous_hours = 2.0
        params = ProductionParams(
            lines=[self.line], skus=[self.sku], shifts=[],
            start_date=self.start
        )

        # Block 2.5h (Violation)
        block = ProductionBlock("B1", "L1", "A",
                                self.start,
                                self.start + timedelta(hours=2.5),
                                25)
        ls = LineSolution("L1", [block])
        sol = ScheduleSolution([ls], params)

        violations = check_max_continuous_run(sol)
        self.assertEqual(len(violations), 1)
        self.assertIn("exceeds max limit", violations[0].message)

        # Block 1.5h (OK)
        block2 = ProductionBlock("B2", "L1", "A",
                                 self.start,
                                 self.start + timedelta(hours=1.5),
                                 15)
        ls.production_blocks = [block2]
        violations = check_max_continuous_run(sol)
        self.assertEqual(len(violations), 0)

    def test_shift_downtime_calculation(self):
        # Shift 08:00-16:00 (8h).
        # Downtime should be 00:00-08:00 and 16:00-24:00 (relative offsets)
        shift = Shift("S1", "Day", time(8,0), time(16,0), ["L1"])
        params = ProductionParams(
            lines=[self.line], skus=[self.sku], shifts=[shift],
            start_date=self.start, planning_horizon_days=1.0
        )

        # Optimizer init triggers _calculate_shift_downtimes
        GeneticOptimizer(params, population_size=10)

        downtimes = self.line.downtime_windows
        # Expect:
        # 1. Start -> 8am (0 -> 8h implied? If start is 8am, then 0 offset is 8am).
        # Wait, start_date is 8:00.
        # Shift starts 8:00. End 16:00.
        # Offset 0 to 8.
        # Next shift (Day 2) starts at T+24h.

        # Correct logic:
        # Start Date 8:00. Shift 8:00.
        # Uptime: 0.0 to 8.0.
        # Next Uptime: 24.0 to 32.0.
        # Downtimes: (8.0, 24.0), (32.0, INF)

        # Let's verify
        self.assertTrue(len(downtimes) >= 1)
        # Check first gap
        # downtime[0] should start around 8.0
        self.assertAlmostEqual(downtimes[0][0], 8.0, delta=0.1)
        self.assertAlmostEqual(downtimes[0][1], 24.0, delta=0.1)

if __name__ == '__main__':
    unittest.main()
