"""Regression tests for solver downtime splitting, shift weekdays, and app wiring."""

import inspect
import os
import random
from pathlib import Path

from core.constraints import validate_solution
from core.objectives import get_demand_fulfillment_pct
from file_io.loader import load_from_json, save_solution_json
from optimizer.genetic import GeneticOptimizer


def test_water_factory_preserves_shift_day_of_week():
    """Shifts loaded from water_factory_config.json keep day_of_week."""
    params = load_from_json("examples/water_factory_config.json")
    day_map = {s.name: s.day_of_week for s in params.shifts}
    assert day_map["Sat Morning"] == 6
    assert day_map["Sun Morning"] == 0
    assert day_map["Mon Morning"] == 1
    assert day_map["Fri Night"] == 5
    assert "Fri Morning" not in day_map


def test_water_factory_full_demand_and_no_dropped_batches():
    """GA must split batches across 23h shift windows and fulfill 100% demand."""
    random.seed(42)
    params = load_from_json("examples/water_factory_config.json")
    optimizer = GeneticOptimizer(params, population_size=30, generations=25)
    solution = optimizer.solve()

    is_feasible, violations = validate_solution(solution, verbose=False)
    hard = [v for v in violations if v.severity == "hard"]
    soft = [v for v in violations if v.severity == "soft"]

    assert is_feasible, f"Hard violations: {hard}"
    assert len(soft) == 0, f"Soft demand violations: {soft}"
    assert get_demand_fulfillment_pct(solution) >= 100.0


def test_repeated_optimizer_init_does_not_duplicate_downtimes():
    """Instantiating GeneticOptimizer repeatedly must not duplicate downtime windows."""
    params = load_from_json("examples/small_factory.json")
    GeneticOptimizer(params, population_size=10, generations=2)
    first_counts = [len(line.downtime_windows) for line in params.lines]

    GeneticOptimizer(params, population_size=10, generations=2)
    second_counts = [len(line.downtime_windows) for line in params.lines]

    assert first_counts == second_counts


def test_main_window_uses_real_save_solution_json_and_no_cwd_log(tmp_path):
    """app.main must not create a CWD log on import and MainWindow must use save_solution_json."""
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        import app.main as app_main

        assert not (Path(tmp_path) / "supply_chain_planner.log").exists()
        assert callable(app_main.main)
    finally:
        os.chdir(old_cwd)

    import app.main_window as mw

    source = inspect.getsource(mw.MainWindow._export_schedule)
    assert "save_solution_to_json" not in source
    assert "save_solution_json" in source
    assert callable(save_solution_json)
