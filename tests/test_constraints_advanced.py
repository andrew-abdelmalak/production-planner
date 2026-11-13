"""
test_constraints_advanced.py - Tests for Advanced Constraints
"""

import unittest
from datetime import datetime, time, timedelta

from core.params import (
    ProductionLine, SKU, Shift, ProductionParams, make_demo_params
)
from core.solution import ProductionBlock, LineSolution, ScheduleSolution
from core.constraints_advanced import (
    ExclusiveSKUConstraint, ShiftRestrictionConstraint,
    SequenceRestrictionConstraint, MinRunLengthConstraint
)

def make_block(sku_id, line_id, start_hour, end_hour, block_id="B1"):
    base = datetime(2025, 2, 1, 0, 0)
    return ProductionBlock(
        block_id=block_id,
        line_id=line_id,
        sku_id=sku_id,
        start_time=base + timedelta(hours=start_hour),
        end_time=base + timedelta(hours=end_hour),
        units_produced=100
    )

class TestExclusiveSKU(unittest.TestCase):
    def setUp(self):
        self.params = make_demo_params()
        self.constraint = ExclusiveSKUConstraint("Excl", "Tests", True, "SKU-A")

    def test_exclusive_valid(self):
        # SKU-A runs at diff times on diff lines
        b1 = make_block("SKU-A", "L1", 0, 5, "B1")
        b2 = make_block("SKU-A", "L2", 5, 10, "B2")
        sol = ScheduleSolution([LineSolution("L1", [b1]), LineSolution("L2", [b2])], self.params)
        
        valid, _ = self.constraint.validate(sol)
        self.assertTrue(valid)

    def test_exclusive_invalid(self):
        # SKU-A runs at same time on diff lines
        b1 = make_block("SKU-A", "L1", 0, 5, "B1")
        b2 = make_block("SKU-A", "L2", 2, 7, "B2") # Overlap 2-5
        sol = ScheduleSolution([LineSolution("L1", [b1]), LineSolution("L2", [b2])], self.params)
        
        valid, msg = self.constraint.validate(sol)
        self.assertFalse(valid)
        self.assertIn("SKU-A runs simultaneously", msg[0])

class TestShiftRestriction(unittest.TestCase):
    def setUp(self):
        self.shift1 = Shift("S1", "Morning", time(6,0), time(14,0), ["L1"])
        self.shift2 = Shift("S2", "Evening", time(14,0), time(22,0), ["L1"])
        self.params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["SKU-A"])],
            skus=[SKU("SKU-A", "A", 100)],
            shifts=[self.shift1, self.shift2]
        )
        self.constraint = ShiftRestrictionConstraint("ShiftTest", "", True, "SKU-A", ["S1"]) # S1 only

    def test_allowed_shift(self):
        # 8 AM is in S1 (6-14)
        base = datetime(2025, 2, 1, 8, 0)
        b1 = ProductionBlock("B1", "L1", "SKU-A", base, base+timedelta(hours=2), 100)
        sol = ScheduleSolution([LineSolution("L1", [b1])], self.params)
        
        valid, _ = self.constraint.validate(sol)
        self.assertTrue(valid)

    def test_forbidden_shift(self):
        # 16:00 (4 PM) is in S2 (14-22), not S1
        base = datetime(2025, 2, 1, 16, 0) 
        b1 = ProductionBlock("B1", "L1", "SKU-A", base, base+timedelta(hours=2), 100)
        sol = ScheduleSolution([LineSolution("L1", [b1])], self.params)
        
        valid, msg = self.constraint.validate(sol)
        self.assertFalse(valid)
        self.assertIn("does not match allowed shifts", msg[0])

class TestSequenceRestriction(unittest.TestCase):
    def setUp(self):
        self.params = make_demo_params()
        self.constraint = SequenceRestrictionConstraint("Seq", "", True, "SKU-A", "SKU-B") # No A -> B

    def test_valid_sequence(self):
        # A -> C -> B
        b1 = make_block("SKU-A", "L1", 0, 1)
        b2 = make_block("SKU-C", "L1", 1, 2)
        b3 = make_block("SKU-B", "L1", 2, 3)
        sol = ScheduleSolution([LineSolution("L1", [b1, b2, b3])], self.params)
        self.assertTrue(self.constraint.validate(sol)[0])

    def test_invalid_sequence(self):
        # A -> B
        b1 = make_block("SKU-A", "L1", 0, 1)
        b2 = make_block("SKU-B", "L1", 1, 2)
        sol = ScheduleSolution([LineSolution("L1", [b1, b2])], self.params)
        self.assertFalse(self.constraint.validate(sol)[0])

class TestMinRunLength(unittest.TestCase):
    def setUp(self):
        self.params = make_demo_params()
        self.constraint = MinRunLengthConstraint("MinRun", "", True, "SKU-A", 5.0) # Min 5h

    def test_valid_run(self):
        b1 = make_block("SKU-A", "L1", 0, 6) # 6h > 5h
        sol = ScheduleSolution([LineSolution("L1", [b1])], self.params)
        self.assertTrue(self.constraint.validate(sol)[0])

    def test_short_run(self):
        b1 = make_block("SKU-A", "L1", 0, 2) # 2h < 5h
        sol = ScheduleSolution([LineSolution("L1", [b1])], self.params)
        self.assertFalse(self.constraint.validate(sol)[0])

if __name__ == '__main__':
    unittest.main()
