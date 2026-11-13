"""
test_otif.py - Tests for OTIF (On-Time In-Full) KPI Calculation
"""

import unittest
from datetime import datetime, time, timedelta

from core.params import (
    ProductionLine, SKU, Shift, ProductionParams
)
from core.solution import ProductionBlock, LineSolution, ScheduleSolution
from core.objectives import objective_otif, objective_otif_detailed


def make_block(sku_id, line_id, units, start_hour, end_hour, block_id="B1"):
    """Helper to create ProductionBlock with proper datetime objects."""
    base = datetime(2025, 2, 1, 0, 0)
    return ProductionBlock(
        block_id=block_id,
        line_id=line_id,
        sku_id=sku_id,
        start_time=base + timedelta(hours=start_hour),
        end_time=base + timedelta(hours=end_hour),
        units_produced=units
    )


class TestOTIFCalculation(unittest.TestCase):
    """Test OTIF percentage calculation."""
    
    def test_all_on_time_in_full(self):
        """100% OTIF when all SKUs are on-time and in-full."""
        due_date = datetime(2025, 2, 10, 0, 0)  # Due Feb 10
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000, due_date=due_date)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
            start_date=datetime(2025, 2, 1, 0, 0),  # Start Feb 1
        )
        
        # Block completes at hour 10 (Feb 1 10:00) - well before due date
        block = make_block("SKU-A", "L1", 1000, 0, 10.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], params)
        
        otif = objective_otif(solution)
        self.assertEqual(otif, 100.0)
    
    def test_in_full_but_late(self):
        """0% OTIF when SKU is in-full but delivered late."""
        due_date = datetime(2025, 2, 1, 5, 0)  # Due Feb 1 5:00
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000, due_date=due_date)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
            start_date=datetime(2025, 2, 1, 0, 0),
        )
        
        # Block completes at hour 10 (Feb 1 10:00) - AFTER due date of 5:00
        block = make_block("SKU-A", "L1", 1000, 0, 10.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], params)
        
        otif = objective_otif(solution)
        self.assertEqual(otif, 0.0)
    
    def test_on_time_but_partial(self):
        """0% OTIF when delivered on-time but not in-full."""
        due_date = datetime(2025, 2, 10, 0, 0)
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000, due_date=due_date)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
            start_date=datetime(2025, 2, 1, 0, 0),
        )
        
        # Only produce 500 units (half of demand)
        block = make_block("SKU-A", "L1", 500, 0, 5.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], params)
        
        otif = objective_otif(solution)
        self.assertEqual(otif, 0.0)
    
    def test_mixed_otif(self):
        """50% OTIF when 1 of 2 SKUs is on-time and in-full."""
        due_date = datetime(2025, 2, 10, 0, 0)
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A", "SKU-B"], base_speed_units_per_hour=100)],
            skus=[
                SKU("SKU-A", "Product A", 1000, due_date=due_date),
                SKU("SKU-B", "Product B", 1000, due_date=due_date),
            ],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
            start_date=datetime(2025, 2, 1, 0, 0),
        )
        
        # SKU-A: 1000 units on time = OTIF
        # SKU-B: only 500 units = NOT OTIF
        block_a = make_block("SKU-A", "L1", 1000, 0, 10.0, "BA")
        block_b = make_block("SKU-B", "L1", 500, 10.0, 15.0, "BB")
        line_sol = LineSolution("L1", [block_a, block_b])
        solution = ScheduleSolution([line_sol], params)
        
        otif = objective_otif(solution)
        self.assertEqual(otif, 50.0)
    
    def test_no_due_date(self):
        """SKUs without due dates are considered on-time."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000)],  # No due_date
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
        
        block = make_block("SKU-A", "L1", 1000, 0, 10.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], params)
        
        # No due date = always on-time if in-full
        otif = objective_otif(solution)
        self.assertEqual(otif, 100.0)
    
    def test_empty_solution(self):
        """Empty solution should have 0% OTIF (no SKUs fulfilled)."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
        
        solution = ScheduleSolution([], params)
        
        otif = objective_otif(solution)
        self.assertEqual(otif, 0.0)


class TestOTIFDetailed(unittest.TestCase):
    """Test detailed OTIF breakdown."""
    
    def test_detailed_breakdown(self):
        """Verify detailed breakdown includes per-SKU status."""
        due_date = datetime(2025, 2, 10, 0, 0)
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000, due_date=due_date)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
            start_date=datetime(2025, 2, 1, 0, 0),
        )
        
        block = make_block("SKU-A", "L1", 1000, 0, 10.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], params)
        
        details = objective_otif_detailed(solution)
        
        self.assertIn("otif_percentage", details)
        self.assertIn("by_sku", details)
        self.assertEqual(details["otif_percentage"], 100.0)
        
        sku_detail = details["by_sku"]["SKU-A"]
        self.assertTrue(sku_detail["in_full"])
        self.assertTrue(sku_detail["on_time"])
        self.assertTrue(sku_detail["is_otif"])


if __name__ == '__main__':
    unittest.main()
