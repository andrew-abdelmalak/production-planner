import unittest
from datetime import datetime, time

from core.objectives import objective_demand_detailed, objective_demand_penalty
from core.params import SKU, ProductionLine, ProductionParams, Shift
from core.solution import LineSolution, ProductionBlock, ScheduleSolution


class TestInventoryLogic(unittest.TestCase):
    def setUp(self):
        self.sku_a = SKU("SKU-A", "Product A", 1000, starting_stock=200,
                        underage_buffer_pct=0.1, overage_buffer_pct=0.1)
        self.sku_b = SKU("SKU-B", "Product B", 1000, starting_stock=1200,
                        underage_buffer_pct=0.0, overage_buffer_pct=0.05)

        self.line = ProductionLine("L1", "Line 1", ["SKU-A", "SKU-B"], 1000.0)
        self.shift = Shift("S1", "Day", time(8,0), time(16,0), ["L1"])

        self.params = ProductionParams([self.line], [self.sku_a, self.sku_b], [self.shift])
        self.solution = ScheduleSolution(line_solutions=[], params=self.params)

    def test_fulfillment_calculation(self):
        """Test calculation of fulfillment ratio including starting stock."""
        # Case 1: SKU-A (Start 200, Produced 0) -> Total 200 / Demand 1000 = 0.2
        fulfillment = self.solution.get_demand_fulfillment()
        self.assertAlmostEqual(fulfillment["SKU-A"], 0.2)

        # Case 2: SKU-B (Start 1200, Produced 0) -> Total 1200 / Demand 1000 = 1.2
        self.assertAlmostEqual(fulfillment["SKU-B"], 1.2)

    def test_underproduction_penalty(self):
        """Test penalty when inventory is below minimum buffer."""
        # SKU-A: Start 200. Min allowed = 1000 * (1 - 0.1) = 900.
        # Shortfall = 900 - 200 = 700.
        # Penalty = 700 * 0.1 (Base) * 1.0 (Priority 5 -> Weight 1.0) = 70.0

        penalty = objective_demand_penalty(self.solution)
        # Note: objective_demand_penalty sums up SKU-A (70.0) + SKU-B (Overproduction)

        # Determine SKU-B penalty (Overproduction)
        # SKU-B: Start 1200. Max allowed = 1000 * (1 + 0.05) = 1050.
        # Excess = 1200 - 1050 = 150.
        # Penalty = 150 * 0.1 * 0.5 * 1.0 = 7.5.

        # Total expected = 70.0 + 7.5 = 77.5
        self.assertAlmostEqual(penalty, 77.5)

    def test_overproduction_penalty(self):
        """Test specifically the overproduction logic."""
        # Create solution with high production for SKU-A
        # Aim for 1200 total (Start 200 + Produce 1000). Max allowed 1100.
        # Min Batch 100.

        block = ProductionBlock("B1", "L1", "SKU-A", datetime.now(), datetime.now(), 1000)
        ls = LineSolution("L1", [block])
        sol = ScheduleSolution([ls], self.params)

        # SKU-A: Total 1200. Max 1100. Excess 100.
        # Penalty = 100 * 0.1 * 0.5 = 5.0.

        # SKU-B: Still 1200 (Start). Max 1050. Excess 150. Penalty 7.5.

        # Total = 12.5
        penalty = objective_demand_penalty(sol)
        self.assertAlmostEqual(penalty, 12.5)

    def test_within_buffer_no_penalty(self):
        """Test zero penalty when within buffer range."""
        # SKU-A Target: 900 to 1100.
        # Produce 800 -> Total 1000. Perfect.

        # SKU-B Target: 1000 to 1050.
        # But Start is 1200. We can't reduce stock.
        # So let's change SKU-B params for this test only.
        self.sku_b.starting_stock = 1000 # Perfect match

        block = ProductionBlock("B1", "L1", "SKU-A", datetime.now(), datetime.now(), 800)
        ls = LineSolution("L1", [block])
        sol = ScheduleSolution([ls], self.params)

        penalty = objective_demand_penalty(sol)
        self.assertEqual(penalty, 0.0)

    def test_objective_detailed(self):
        """Test detailed reporting structure."""
        details = objective_demand_detailed(self.solution)

        d_a = details["SKU-A"]
        self.assertEqual(d_a["status"], "UNDER")
        self.assertEqual(d_a["starting_stock"], 200)
        self.assertEqual(d_a["total_inventory"], 200)
        self.assertEqual(d_a["min_allowed"], 900)

        d_b = details["SKU-B"]
        self.assertEqual(d_b["status"], "OVER")
        self.assertEqual(d_b["excess"], 150)

if __name__ == '__main__':
    unittest.main()
