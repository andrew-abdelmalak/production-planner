"""
test_params.py - Tests for Parameter Data Structures
"""

import unittest
from datetime import time

from core.params import SKU, ProductionLine, ProductionParams, Shift


class TestProductionLine(unittest.TestCase):
    def test_line_speed(self):
        line = ProductionLine(
            line_id="L1", name="Line 1", compatible_skus=["S1", "S2"],
            base_speed_units_per_hour=100.0,
            sku_speed_multipliers={"S2": 0.5}
        )
        self.assertEqual(line.get_speed_for_sku("S1"), 100.0)
        self.assertEqual(line.get_speed_for_sku("S2"), 50.0)

    def test_compatibility(self):
        line = ProductionLine(
            line_id="L1", name="Line 1", compatible_skus=["S1"]
        )
        self.assertTrue(line.can_produce("S1"))
        self.assertFalse(line.can_produce("S2"))

class TestProductionParams(unittest.TestCase):
    def test_validation(self):
        # Valid case
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["S1"])],
            skus=[SKU("S1", "SKU 1", 100)],
            changeover_matrices=[],
            shifts=[Shift("SH1", "Shift 1", time(8,0), time(16,0), ["L1"])]
        )
        # Should not raise
        params.validate()

    def test_invalid_line_reference(self):
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["S1"])],
            skus=[SKU("S1", "SKU 1", 100)],
            shifts=[Shift("SH1", "Shift 1", time(8,0), time(16,0), ["L2"])] # L2 missing
        )
        with self.assertRaises(ValueError):
            params.validate()

if __name__ == '__main__':
    unittest.main()
