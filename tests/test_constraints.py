"""
test_constraints.py - Tests for Constraint Validation System
"""

import unittest
from datetime import datetime, time, timedelta

from core.params import (
    ProductionLine, SKU, ChangeoverMatrix, Shift, ProductionParams, make_demo_params
)
from core.solution import ProductionBlock, LineSolution, ScheduleSolution
from core.constraints import (
    validate_solution,
    check_line_compatibility,
    check_no_overlap,
    check_changeover_time,
    check_min_batch_size,
    check_non_negative,
    check_time_ordering,
    check_demand_fulfillment,
)


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


class TestLineCompatibility(unittest.TestCase):
    """Test that SKUs can only run on compatible lines."""
    
    def setUp(self):
        self.params = ProductionParams(
            lines=[
                ProductionLine("L1", "Line 1", ["SKU-A", "SKU-B"]),
                ProductionLine("L2", "Line 2", ["SKU-C"]),
            ],
            skus=[
                SKU("SKU-A", "Product A", 1000),
                SKU("SKU-B", "Product B", 1000),
                SKU("SKU-C", "Product C", 1000),
            ],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1", "L2"])],
        )
    
    def test_valid_compatibility(self):
        """SKU-A on L1 should be valid."""
        block = make_block("SKU-A", "L1", 500, 0, 5.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_line_compatibility(solution)
        self.assertEqual(len(violations), 0)
    
    def test_invalid_compatibility(self):
        """SKU-A on L2 should be invalid (L2 only supports SKU-C)."""
        block = make_block("SKU-A", "L2", 500, 0, 5.0)
        line_sol = LineSolution("L2", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_line_compatibility(solution)
        self.assertEqual(len(violations), 1)
        self.assertIn("SKU-A", violations[0].message)


class TestNoOverlap(unittest.TestCase):
    """Test that blocks on the same line don't overlap."""
    
    def setUp(self):
        self.params = make_demo_params()
    
    def test_no_overlap_valid(self):
        """Non-overlapping blocks should pass."""
        block1 = make_block("SKU-001", "LINE-A", 500, 0, 5.0, "B1")
        block2 = make_block("SKU-002", "LINE-A", 500, 5.0, 10.0, "B2")
        line_sol = LineSolution("LINE-A", [block1, block2])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_no_overlap(solution)
        self.assertEqual(len(violations), 0)
    
    def test_overlap_invalid(self):
        """Overlapping blocks should fail."""
        block1 = make_block("SKU-001", "LINE-A", 500, 0, 6.0, "B1")
        block2 = make_block("SKU-002", "LINE-A", 500, 5.0, 10.0, "B2")  # Starts before block1 ends
        line_sol = LineSolution("LINE-A", [block1, block2])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_no_overlap(solution)
        self.assertEqual(len(violations), 1)


class TestMinBatchSize(unittest.TestCase):
    """Test that production meets minimum batch size."""
    
    def setUp(self):
        self.params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"])],
            skus=[SKU("SKU-A", "Product A", 1000, min_batch_size=500)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
    
    def test_meets_min_batch(self):
        """Block with 500 units should pass (min is 500)."""
        block = make_block("SKU-A", "L1", 500, 0, 5.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_min_batch_size(solution)
        self.assertEqual(len(violations), 0)
    
    def test_below_min_batch(self):
        """Block with 100 units should fail (min is 500)."""
        block = make_block("SKU-A", "L1", 100, 0, 1.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_min_batch_size(solution)
        self.assertEqual(len(violations), 1)


class TestNonNegative(unittest.TestCase):
    """Test that all quantities are non-negative."""
    
    def setUp(self):
        self.params = make_demo_params()
    
    def test_valid_positive_values(self):
        """Positive values should pass."""
        block = make_block("SKU-001", "LINE-A", 500, 0, 5.0)
        line_sol = LineSolution("LINE-A", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_non_negative(solution)
        self.assertEqual(len(violations), 0)
    
    def test_negative_units(self):
        """Negative units should fail."""
        block = make_block("SKU-001", "LINE-A", -500, 0, 5.0)
        line_sol = LineSolution("LINE-A", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_non_negative(solution)
        self.assertGreater(len(violations), 0)


class TestTimeOrdering(unittest.TestCase):
    """Test that block end time is after start time."""
    
    def setUp(self):
        self.params = make_demo_params()
    
    def test_valid_time_order(self):
        """End after start should pass."""
        block = make_block("SKU-001", "LINE-A", 500, 0, 5.0)
        line_sol = LineSolution("LINE-A", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_time_ordering(solution)
        self.assertEqual(len(violations), 0)
    
    def test_invalid_time_order(self):
        """End before start should fail."""
        # Create block where end < start (hour 0 to hour -5, effectively)
        base = datetime(2025, 2, 1, 5, 0)
        block = ProductionBlock(
            block_id="B1", line_id="LINE-A", sku_id="SKU-001",
            start_time=base,
            end_time=base - timedelta(hours=5),  # end before start
            units_produced=500
        )
        line_sol = LineSolution("LINE-A", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_time_ordering(solution)
        self.assertGreater(len(violations), 0)


class TestDemandFulfillment(unittest.TestCase):
    """Test demand fulfillment soft constraint."""
    
    def setUp(self):
        self.params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 1000)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
    
    def test_full_demand_met(self):
        """All demand met should pass with no violations."""
        block = make_block("SKU-A", "L1", 1000, 0, 10.0)
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_demand_fulfillment(solution)
        self.assertEqual(len(violations), 0)
    
    def test_partial_demand_met(self):
        """Partial demand should generate soft violation."""
        block = make_block("SKU-A", "L1", 500, 0, 5.0)  # Only 500 of 1000
        line_sol = LineSolution("L1", [block])
        solution = ScheduleSolution([line_sol], self.params)
        
        violations = check_demand_fulfillment(solution)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, "soft")


class TestValidateSolution(unittest.TestCase):
    """Test the main validate_solution function."""
    
    def setUp(self):
        self.params = make_demo_params()
    
    def test_valid_solution(self):
        """A properly constructed solution should be feasible."""
        # Create params with start_date matching block times
        params = ProductionParams(
            lines=[ProductionLine("LINE-A", "Line A", ["SKU-001"], base_speed_units_per_hour=100, max_continuous_hours=24.0)],
            skus=[SKU("SKU-001", "SKU 001", 1000, min_batch_size=100)],
            shifts=[Shift("S1", "Shift 1", time(0, 0), time(23, 59), ["LINE-A"])],
            start_date=datetime(2025, 2, 1, 0, 0),
            planning_horizon_days=7
        )
        block = make_block("SKU-001", "LINE-A", 1000, 0, 10.0)
        line_sol = LineSolution("LINE-A", [block])
        solution = ScheduleSolution([line_sol], params)
        
        is_feasible, violations = validate_solution(solution)
        self.assertTrue(is_feasible)
    
    def test_empty_solution(self):
        """Empty solution should be feasible but may have soft violations."""
        solution = ScheduleSolution([], self.params)
        
        is_feasible, violations = validate_solution(solution)
        self.assertTrue(is_feasible)


if __name__ == '__main__':
    unittest.main()
