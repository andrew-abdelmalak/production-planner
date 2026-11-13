"""
test_optimizer.py - Tests for Genetic Optimizer
"""

import unittest
from datetime import datetime

from core.params import make_demo_params
from optimizer.genetic import GeneticOptimizer
from core.constraints import validate_solution

class TestGeneticOptimizer(unittest.TestCase):
    def setUp(self):
        # Use demo params which are already validated and consistent
        self.params = make_demo_params()
        # Reduce demand to make test faster
        for sku in self.params.skus:
            sku.demand_units = sku.min_batch_size * 2
            
    def test_optimizer_feasibility(self):
        # Use small population/gens for speed
        optimizer = GeneticOptimizer(
            self.params, 
            population_size=10, 
            generations=5
        )
        solution = optimizer.solve()
        
        self.assertIsNotNone(solution)
        is_feasible, violations = validate_solution(solution)
        self.assertTrue(is_feasible, f"Solution infeasible: {violations}")
        
    def test_makespan(self):
        optimizer = GeneticOptimizer(
            self.params, 
            population_size=10, 
            generations=5
        )
        solution = optimizer.solve()
        makespan = solution.get_makespan_hours()
        self.assertGreater(makespan, 0)
        
    def test_total_units(self):
        optimizer = GeneticOptimizer(
            self.params, 
            population_size=10, 
            generations=5
        )
        solution = optimizer.solve()
        expected_units = sum(sku.demand_units for sku in self.params.skus)
        # In a perfect world, we produce exactly what's needed
        # But batch sizing might cause slight overproduction
        self.assertGreaterEqual(solution.get_total_units(), expected_units)

if __name__ == '__main__':
    unittest.main()
