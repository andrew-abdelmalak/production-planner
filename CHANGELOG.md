# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Packaged the project with `pyproject.toml`, `uv.lock` (`exclude-newer = "14 days"`), and console entry points `production-planner` and `production-planner-gui`.
- Added generic factory CSV directory (`templates/*.csv`) and multi-sheet Excel (`templates/factory_template.xlsx`) loaders, exporters, and [docs/input-format.md](docs/input-format.md).
- Added headless CLI (`app/cli.py`) supporting JSON, CSV, and Excel inputs/outputs, ensemble runs, scenario presets, and deterministic `--seed` runs.
- Added regression tests (`tests/test_regression_fixes.py`), tabular/CLI/Qt offscreen tests (`tests/test_tabular_and_cli.py`), Ruff linting, GitHub Actions CI, and community health files.

### Fixed
- Preserved `Shift.day_of_week` parsing/serialization in `core/params.py` and `file_io/loader.py`, including weekday-specific shifts (such as Friday night-only operations).
- Rewrote `GeneticOptimizer._calculate_shift_downtimes()` and `_chromosome_to_solution()` so overnight shifts compute windows idempotently and production blocks split cleanly across cleaning/shift boundaries instead of being dropped.
- Returned zero changeover time and cost when consecutive blocks run the same SKU even if `changeover_matrices` is empty.
- Wired `ConfigPanel` horizon, changeover, and cleaning spinboxes to `ProductionParams`, fixed `MainWindow._export_schedule()` to call `save_solution_json` (plus `.csv`/`.xlsx`), and removed import-time `supply_chain_planner.log` side effects.
- Updated `scripts/build_exe.py` from `PyQt6` to `PySide6`.

## [0.1.0] - 2026-11-14

### Added
- Initial public baseline with core scheduling dataclasses, hard/soft constraints, genetic and ensemble optimizers, JSON loader, sample water bottling factory config, and PySide6 desktop Gantt application.
