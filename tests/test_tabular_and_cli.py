"""Tests for tabular CSV/Excel I/O, CLI execution, and offscreen Qt smoke checks."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cli import main as cli_main
from file_io.tabular import (
    load_from_csv_dir,
    load_from_excel,
    load_params,
    save_solution_csv,
    save_solution_excel,
    save_to_csv_dir,
    save_to_excel,
)
from optimizer.genetic import GeneticOptimizer

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_csv_and_excel_round_trip_parity(tmp_path):
    """Exporting JSON config to CSV dir and Excel and reloading preserves key factory fields."""
    original = load_params(REPO_ROOT / "examples" / "small_factory.json")

    csv_dir = tmp_path / "factory_csv"
    xlsx_path = tmp_path / "factory.xlsx"
    save_to_csv_dir(original, csv_dir)
    save_to_excel(original, xlsx_path)

    from_csv = load_from_csv_dir(csv_dir)
    from_xlsx = load_from_excel(xlsx_path)

    for loaded in (from_csv, from_xlsx):
        assert loaded.planning_horizon_days == original.planning_horizon_days
        assert loaded.start_date == original.start_date
        assert len(loaded.lines) == len(original.lines)
        assert len(loaded.skus) == len(original.skus)
        assert len(loaded.shifts) == len(original.shifts)

        for orig_line, new_line in zip(original.lines, loaded.lines, strict=True):
            assert new_line.line_id == orig_line.line_id
            assert set(new_line.compatible_skus) == set(orig_line.compatible_skus)
            for sku_id in orig_line.compatible_skus:
                orig_speed = orig_line.get_speed_for_sku(sku_id)
                new_speed = new_line.get_speed_for_sku(sku_id)
                assert new_speed == pytest.approx(orig_speed)

        for orig_sku, new_sku in zip(original.skus, loaded.skus, strict=True):
            assert new_sku.sku_id == orig_sku.sku_id
            assert new_sku.demand_units == orig_sku.demand_units
            assert new_sku.priority == orig_sku.priority
            assert new_sku.min_batch_size == orig_sku.min_batch_size


def test_load_params_auto_detection_and_errors(tmp_path):
    """Auto-detection resolves .json, .xlsx, directory, or .csv inside directory; rejects bad input."""
    assert len(load_params(REPO_ROOT / "templates").lines) == 2
    assert len(load_params(REPO_ROOT / "templates" / "lines.csv").lines) == 2
    assert len(load_params(REPO_ROOT / "templates" / "factory_template.xlsx").lines) == 2

    bad_file = tmp_path / "factory.txt"
    bad_file.write_text("invalid")
    with pytest.raises(ValueError, match="Cannot infer input format"):
        load_params(bad_file)

    empty_dir = tmp_path / "empty_csv"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_from_csv_dir(empty_dir)


def test_solution_export_csv_and_excel(tmp_path):
    """Solving small_factory exports valid CSV rows and multi-sheet Excel summary."""
    random.seed(42)
    params = load_params(REPO_ROOT / "templates" / "factory_template.xlsx")
    optimizer = GeneticOptimizer(params, population_size=15, generations=10, verbose=False)
    solution = optimizer.solve()
    blocks = solution.get_all_blocks_sorted()
    assert len(blocks) > 0

    csv_out = tmp_path / "schedule.csv"
    xlsx_out = tmp_path / "schedule.xlsx"
    save_solution_csv(solution, csv_out)
    save_solution_excel(solution, xlsx_out)

    csv_lines = csv_out.read_text(encoding="utf-8").strip().splitlines()
    assert len(csv_lines) == len(blocks) + 1
    assert "block_id,line_id,sku_id" in csv_lines[0]

    wb = load_workbook(xlsx_out, read_only=True)
    try:
        assert set(wb.sheetnames) == {"Summary", "Schedule", "Fulfillment"}
    finally:
        wb.close()


def test_cli_end_to_end_formats(tmp_path):
    """CLI solves JSON, CSV directory, and Excel inputs reproducibly and exports outputs."""
    json_out = tmp_path / "water_schedule.json"
    rc_water = cli_main([
        "-i",
        str(REPO_ROOT / "examples" / "water_factory_config.json"),
        "-o",
        str(json_out),
        "--population",
        "20",
        "--generations",
        "15",
        "--seed",
        "42",
        "--quiet",
    ])
    assert rc_water == 0
    assert json_out.exists()

    xlsx_out = tmp_path / "template_schedule.xlsx"
    rc_xlsx = cli_main([
        "-i",
        str(REPO_ROOT / "templates" / "factory_template.xlsx"),
        "-o",
        str(xlsx_out),
        "--population",
        "15",
        "--generations",
        "10",
        "--seed",
        "42",
        "--quiet",
    ])
    assert rc_xlsx == 0
    assert xlsx_out.exists()

    csv_out = tmp_path / "csv_schedule.csv"
    rc_csv = cli_main([
        "-i",
        str(REPO_ROOT / "templates"),
        "-o",
        str(csv_out),
        "--population",
        "15",
        "--generations",
        "10",
        "--runs",
        "2",
        "--scenario",
        "balanced",
        "--seed",
        "42",
        "--quiet",
    ])
    assert rc_csv == 0
    assert csv_out.exists()


def test_offscreen_qt_main_window_smoke():
    """PySide6 MainWindow initializes offscreen, loads demo parameters, and renders panels."""
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    assert app is not None

    window = MainWindow()
    assert window.params is not None
    assert window.config_panel.horizon_spin.value() == window.params.planning_horizon_days
    window.close()
