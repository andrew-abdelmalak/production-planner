"""
test_loader_advanced.py - Advanced Tests for Loader
"""

import json
import os
import unittest
from datetime import time

from core.params import SKU, ChangeoverMatrix, ProductionLine, ProductionParams, Shift
from core.solution import LineSolution, ProductionBlock, ScheduleSolution
from file_io.loader import load_from_json, save_solution_json, save_to_json


class TestLoaderAdvanced(unittest.TestCase):

    def test_save_load_cycle(self):
        """Test full save -> load cycle for params."""
        params = ProductionParams(
            lines=[ProductionLine("L1", "Line 1", ["S1"], 100.0, 24, 30, 90.0)],
            skus=[SKU("S1", "SKU 1", 500, priority=1, min_batch_size=100)],
            shifts=[Shift("SH1", "Shift 1", time(8,0), time(16,0), ["L1"])],
            changeover_matrices=[ChangeoverMatrix("L1", {("S1","S1"):0}, {}, 20, 10)]
        )

        filename = "test_params_cycle.json"
        try:
            save_to_json(params, filename)
            loaded = load_from_json(filename)

            self.assertEqual(len(loaded.lines), 1)
            self.assertEqual(loaded.lines[0].line_id, "L1")
            self.assertEqual(loaded.skus[0].sku_id, "S1")
            self.assertEqual(loaded.shifts[0].shift_id, "SH1")

        finally:
            if os.path.exists(filename):
                os.remove(filename)

    def test_load_malformed(self):
        """Test loading invalid JSON."""
        with open("bad.json", "w") as f:
            f.write("{ bad json ")
        try:
            with self.assertRaises(ValueError):
                load_from_json("bad.json")
        finally:
            if os.path.exists("bad.json"):
                os.remove("bad.json")

    def test_missing_file(self):
        """Test loading non-existent file."""
        with self.assertRaises(FileNotFoundError):
            load_from_json("non_existent_file_123.json")

    def test_save_solution(self):
        """Test saving a solution to JSON."""
        from datetime import datetime
        params = ProductionParams([], [], [])
        block = ProductionBlock("B1", "L1", "S1", datetime(2025,1,1,10,0), datetime(2025,1,1,12,0), 200)
        sol = ScheduleSolution([LineSolution("L1", [block])], params)

        filename = "test_sol.json"
        try:
            save_solution_json(sol, filename)
            with open(filename) as f:
                data = json.load(f)

            self.assertIn("line_solutions", data)
            self.assertEqual(data["line_solutions"][0]["line_id"], "L1")
            self.assertEqual(data["line_solutions"][0]["blocks"][0]["block_id"], "B1")

        finally:
            if os.path.exists(filename):
                os.remove(filename)

if __name__ == '__main__':
    unittest.main()
