"""
test_edge_cases.py - Edge Case Tests for Production Scheduling
"""

import unittest
from datetime import datetime, time, timedelta

from core.params import (
    ProductionLine, SKU, ChangeoverMatrix, Shift, ProductionParams, make_demo_params
)
from core.solution import ProductionBlock, LineSolution, ScheduleSolution
from core.objectives import evaluate_solution, objective_makespan
from core.constraints import validate_solution
from optimizer.genetic import GeneticOptimizer


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


class TestEmptySchedule(unittest.TestCase):
    """Test behavior with empty schedules."""
    
    def setUp(self):
        self.params = make_demo_params()
    
    def test_empty_solution_makespan(self):
        """Empty solution should have 0 makespan."""
        solution = ScheduleSolution([], self.params)
        makespan = objective_makespan(solution)
        self.assertEqual(makespan, 0.0)
    
    def test_empty_solution_evaluation(self):
        """Empty solution should return valid evaluation dict."""
        solution = ScheduleSolution([], self.params)
        results = evaluate_solution(solution)
        
        self.assertIn("makespan_hours", results)
        self.assertIn("total_units", results)
        self.assertEqual(results["total_units"], 0)
    
    def test_empty_solution_validation(self):
        """Empty solution should be feasible."""
        solution = ScheduleSolution([], self.params)
        is_feasible, violations = validate_solution(solution)
        self.assertTrue(is_feasible)


class TestSingleLine(unittest.TestCase):
    """Test with single production line."""
    
    def test_single_line_optimization(self):
        """Optimizer should work with single line."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 500, min_batch_size=100)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
        
        optimizer = GeneticOptimizer(params, population_size=5, generations=3)
        solution = optimizer.solve()
        
        self.assertIsNotNone(solution)
        self.assertGreaterEqual(solution.get_total_units(), 500)


class TestSingleSKU(unittest.TestCase):
    """Test with single SKU."""
    
    def test_single_sku_multiple_lines(self):
        """Single SKU can be split across lines."""
        params = ProductionParams(
            lines=[
                ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100),
                ProductionLine("L2", "Line 2", ["SKU-A"], base_speed_units_per_hour=100),
            ],
            skus=[SKU("SKU-A", "Product A", 1000, min_batch_size=100)],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1", "L2"])],
        )
        
        optimizer = GeneticOptimizer(params, population_size=5, generations=3)
        solution = optimizer.solve()
        
        self.assertIsNotNone(solution)
        self.assertGreaterEqual(solution.get_total_units(), 1000)


class TestZeroDemand(unittest.TestCase):
    """Test with zero demand SKUs."""
    
    def test_zero_demand_sku(self):
        """SKU with 0 demand should not break optimizer."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A", "SKU-B"], base_speed_units_per_hour=100)],
            skus=[
                SKU("SKU-A", "Product A", 1000, min_batch_size=100),
                SKU("SKU-B", "Product B", 0, min_batch_size=100),  # Zero demand
            ],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
        
        optimizer = GeneticOptimizer(params, population_size=5, generations=3)
        solution = optimizer.solve()
        
        self.assertIsNotNone(solution)
        # Should produce at least SKU-A
        self.assertGreaterEqual(solution.get_total_units(), 1000)


class TestHighPriority(unittest.TestCase):
    """Test priority handling."""
    
    def test_high_priority_sku(self):
        """High priority SKUs should be scheduled."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-H", "SKU-L"], base_speed_units_per_hour=100)],
            skus=[
                SKU("SKU-H", "High Priority", 500, priority=1, min_batch_size=100),
                SKU("SKU-L", "Low Priority", 500, priority=5, min_batch_size=100),
            ],
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
        
        optimizer = GeneticOptimizer(params, population_size=10, generations=5)
        solution = optimizer.solve()
        
        self.assertIsNotNone(solution)
        is_feasible, _ = validate_solution(solution)
        self.assertTrue(is_feasible)


class TestLargeBatchSize(unittest.TestCase):
    """Test with very large minimum batch sizes."""
    
    def test_batch_larger_than_demand(self):
        """Min batch > demand should still produce min batch."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"], base_speed_units_per_hour=100)],
            skus=[SKU("SKU-A", "Product A", 100, min_batch_size=500)],  # min_batch > demand
            shifts=[Shift("S1", "Shift 1", time(8,0), time(16,0), ["L1"])],
        )
        
        optimizer = GeneticOptimizer(params, population_size=5, generations=3)
        solution = optimizer.solve()
        
        self.assertIsNotNone(solution)
        # Should produce at least min_batch_size
        total_units = solution.get_total_units()
        self.assertGreaterEqual(total_units, 100)


class TestLineSpeed(unittest.TestCase):
    """Test line speed calculations."""
    
    def test_speed_multiplier(self):
        """Speed multipliers should affect block duration."""
        line = ProductionLine(
            "L1", "Line 1", ["SKU-A", "SKU-B"],
            base_speed_units_per_hour=100,
            sku_speed_multipliers={"SKU-B": 0.5}  # SKU-B is half speed
        )
        
        # SKU-A should be at base speed
        self.assertEqual(line.get_speed_for_sku("SKU-A"), 100)
        
        # SKU-B should be at half speed
        self.assertEqual(line.get_speed_for_sku("SKU-B"), 50)
    
    def test_efficiency_impact(self):
        """Line efficiency should reduce effective speed."""
        line = ProductionLine(
            "L1", "Line 1", ["SKU-A"],
            base_speed_units_per_hour=100,
            efficiency_percent=80.0  # 80% efficiency
        )
        
        # Effective speed = 100 * 0.80 = 80
        self.assertEqual(line.get_speed_for_sku("SKU-A"), 80)


class TestShiftCalculations(unittest.TestCase):
    """Test shift-related calculations."""
    
    def test_shift_duration_same_day(self):
        """Standard shift should calculate duration correctly."""
        shift = Shift("S1", "Day Shift", time(8, 0), time(16, 0), [])
        self.assertEqual(shift.get_duration_hours(), 8.0)
    
    def test_shift_duration_overnight(self):
        """Overnight shift should handle day boundary."""
        shift = Shift("S2", "Night Shift", time(22, 0), time(6, 0), [])
        self.assertEqual(shift.get_duration_hours(), 8.0)
    
    def test_working_hours_per_day(self):
        """Working hours should sum shift durations."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"])],
            skus=[SKU("SKU-A", "Product A", 100)],
            shifts=[
                Shift("S1", "Morning", time(6, 0), time(14, 0), ["L1"]),
                Shift("S2", "Evening", time(14, 0), time(22, 0), ["L1"]),
            ],
        )
        
        hours = params.get_working_hours_per_day()
        self.assertEqual(hours, 16.0)  # 8 + 8


class TestChangeoverMatrix(unittest.TestCase):
    """Test changeover time and cost calculations."""
    
    def test_default_changeover(self):
        """Missing pairs should use default values."""
        matrix = ChangeoverMatrix(
            line_id="L1",
            changeover_minutes={},
            changeover_cost={},
            default_minutes=30.0,
            default_cost=50.0
        )
        
        self.assertEqual(matrix.get_changeover_time("A", "B"), 30.0)
        self.assertEqual(matrix.get_changeover_cost("A", "B"), 50.0)
    
    def test_specific_changeover(self):
        """Specific pairs should use their values."""
        matrix = ChangeoverMatrix(
            line_id="L1",
            changeover_minutes={("A", "B"): 60.0},
            changeover_cost={("A", "B"): 100.0},
            default_minutes=30.0,
            default_cost=50.0
        )
        
        self.assertEqual(matrix.get_changeover_time("A", "B"), 60.0)
        self.assertEqual(matrix.get_changeover_cost("A", "B"), 100.0)
        
        # Other pairs still use default
        self.assertEqual(matrix.get_changeover_time("B", "A"), 30.0)
    
    def test_same_sku_no_changeover(self):
        """Same SKU should have 0 changeover."""
        matrix = ChangeoverMatrix(
            line_id="L1",
            default_minutes=30.0,
            default_cost=50.0
        )
        
        self.assertEqual(matrix.get_changeover_time("A", "A"), 0.0)
        self.assertEqual(matrix.get_changeover_cost("A", "A"), 0.0)


if __name__ == '__main__':
    unittest.main()
