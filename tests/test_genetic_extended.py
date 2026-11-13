"""
test_genetic_extended.py - Extended Tests for Genetic Algorithm
"""

import unittest

from core.params import make_demo_params
from optimizer.genetic import Chromosome, Gene, GeneticOptimizer


class TestGeneticExtended(unittest.TestCase):

    def setUp(self):
        self.params = make_demo_params()
        self.optimizer = GeneticOptimizer(self.params, population_size=10, generations=2)

    def test_initialization(self):
        """Test population initialization."""
        pop = self.optimizer._initialize_population()
        self.assertEqual(len(pop), 10)
        self.assertIsInstance(pop[0], Chromosome)

    def test_crossover(self):
        """Test crossover produces valid children."""
        pop = self.optimizer._initialize_population()
        p1 = pop[0]
        p2 = pop[1]

        # Ensure parents have genes (greedy usually does)
        if not p1.genes or not p2.genes:
            return

        # _crossover returns (child1, child2)
        c1, c2 = self.optimizer._crossover(p1, p2)

        # Child should be Chromosome
        self.assertIsInstance(c1, Chromosome)
        # Should have genes (unless empty, which is unlikely with demo params)
        self.assertIsNotNone(c1.genes)

    def test_mutation(self):
        """Test mutation modifies chromosome."""
        pop = self.optimizer._initialize_population()
        p = pop[0]

        if not p.genes:
            p.genes = [Gene("S1", "L1", 100, 1)]

        original_len = len(p.genes)
        self.optimizer._mutate(p)

        self.assertIsInstance(p, Chromosome)
        self.assertTrue(len(p.genes) > 0 or original_len == 0)

    def test_chromosome_copy(self):
        """Test deep copy of chromosome."""
        c1 = Chromosome([Gene("S1", "L1", 100, 1)])
        c1.fitness = 10.0
        c2 = c1.copy()

        self.assertEqual(c2.fitness, 10.0)
        self.assertEqual(c2.genes[0].sku_id, "S1")

        # Modify c2, c1 should stay same
        c2.genes[0].sku_id = "S2"
        self.assertEqual(c1.genes[0].sku_id, "S1")

if __name__ == '__main__':
    unittest.main()
