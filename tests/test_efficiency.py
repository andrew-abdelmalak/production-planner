import unittest

from core.params import ProductionLine
from file_io.loader import _params_to_dict, _parse_params


class TestEfficiency(unittest.TestCase):
    def test_efficiency_calculation(self):
        # Create a line with 1000 base speed and 90% efficiency
        line = ProductionLine(
            line_id="L1",
            name="Test Line",
            compatible_skus=["S1"],
            base_speed_units_per_hour=1000.0,
            efficiency_percent=90.0
        )

        # Speed should be 1000 * 0.90 = 900
        speed = line.get_speed_for_sku("S1")
        self.assertEqual(speed, 900.0)

        # Duration for 900 units should be 1 hour
        # Duration = Quantity / Speed
        duration = 900 / speed
        self.assertEqual(duration, 1.0)

        # Duration for 1000 units should be 1.11 hours
        duration_full = 1000 / speed
        self.assertAlmostEqual(duration_full, 1.11111111, places=5)

    def test_json_serialization(self):
        # create dict with efficiency
        data = {
            "lines": [{
                "line_id": "L1",
                "compatible_skus": ["S1"],
                "base_speed_units_per_hour": 100.0,
                "efficiency_percent": 50.0
            }],
            "skus": [{
                "sku_id": "S1",
                "demand_units": 100
            }],
            "shifts": []
        }

        # Parse
        params = _parse_params(data)
        line = params.lines[0]
        self.assertEqual(line.efficiency_percent, 50.0)

        # Serialize back
        output = _params_to_dict(params)
        self.assertEqual(output["lines"][0]["efficiency_percent"], 50.0)

if __name__ == '__main__':
    unittest.main()
