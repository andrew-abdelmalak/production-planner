"""
loader.py - JSON Input/Output for Production Scheduling

Handles loading parameters from JSON files and saving solutions.
"""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any

from core.params import (
    SKU,
    ChangeoverMatrix,
    ProductionLine,
    ProductionParams,
    Shift,
)
from core.solution import ScheduleSolution

# ========================================
# JSON Loading
# ========================================

def load_from_json(file_path: str) -> ProductionParams:
    """
    Load production parameters from a JSON file.

    Args:
        file_path: Path to JSON file

    Returns:
        ProductionParams: Loaded and validated parameters

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or missing required fields
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {file_path}")

    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in file {file_path}: {str(e)}") from e

    return _parse_params(data)


def _validate_required_field(data: dict, field: str, context: str) -> Any:
    """Validate that a required field exists and is not None."""
    if field not in data:
        raise ValueError(f"Missing required field '{field}' in {context}")
    return data[field]


def _validate_positive_number(value: Any, field: str, context: str) -> float:
    """Validate that a value is a positive number."""
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"'{field}' in {context} must be a number, got: {type(value).__name__}"
        ) from exc
    if num < 0:
        raise ValueError(f"'{field}' in {context} must be non-negative, got: {num}")
    return num


def _parse_params(data: dict[str, Any]) -> ProductionParams:
    """Parse JSON data into ProductionParams with validation.

    Supports both old format (line_id, sku_id, compatible_skus) and
    new format (name as primary, sku.line_speeds).
    """

    # Validate top-level structure
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got: {type(data).__name__}")

    # Get global settings
    settings = data.get("settings", {})
    default_changeover = settings.get("changeover_minutes", settings.get("default_changeover_minutes", 120))

    # Parse production lines first (needed to derive sku compatibility)
    lines = []
    line_name_to_id = {}  # Map line names to IDs for new format

    for i, line_data in enumerate(data.get("lines", [])):
        # Support both old format (line_id) and new format (name only)
        line_id = line_data.get("line_id", line_data.get("name", f"LINE-{i+1}"))
        line_name = line_data.get("name", line_id)
        line_name_to_id[line_name] = line_id

        lines.append(ProductionLine(
            line_id=line_id,
            name=line_name,
            compatible_skus=line_data.get("compatible_skus", []),  # Will be filled later if using new format
            base_speed_units_per_hour=line_data.get("base_speed_units_per_hour", 1.0),
            sku_speed_multipliers=line_data.get("sku_speed_multipliers", {}),
            max_continuous_hours=line_data.get("max_continuous_hours", 24.0),
            cleaning_time_minutes=line_data.get("cleaning_time_minutes", settings.get("daily_cleaning_minutes", 60.0)),
            efficiency_percent=line_data.get("efficiency_percent", 100.0),
            downtime_windows=[(w["start_hour"], w["end_hour"]) for w in line_data.get("downtime_windows", [])],
        ))

    # Parse SKUs
    skus = []
    sku_line_speeds = {}  # Store line_speeds for later processing

    for i, sku_data in enumerate(data.get("skus", [])):
        due_date = None
        if "due_date" in sku_data:
            due_date = datetime.fromisoformat(sku_data["due_date"])

        # Support both old format (sku_id) and new format (name only)
        sku_id = sku_data.get("sku_id", sku_data.get("name", f"SKU-{i+1}"))
        sku_name = sku_data.get("name", sku_id)

        # Store line_speeds if present (new format)
        if "line_speeds" in sku_data:
            sku_line_speeds[sku_id] = sku_data["line_speeds"]

        skus.append(SKU(
            sku_id=sku_id,
            name=sku_name,
            demand_units=sku_data.get("demand_units", 0),
            priority=sku_data.get("priority", 5),
            due_date=due_date,
            min_batch_size=sku_data.get("min_batch_size", 100),
            starting_stock=sku_data.get("starting_stock", 0),
            underage_buffer_pct=sku_data.get("underage_buffer_pct", 0.0),
            overage_buffer_pct=sku_data.get("overage_buffer_pct", 0.0),
        ))

    # If using new format (sku.line_speeds), update lines with compatible_skus and speed multipliers
    if sku_line_speeds:
        for line in lines:
            compatible = []
            speed_multipliers = {}

            for sku_id, line_speeds in sku_line_speeds.items():
                # line_speeds uses line names as keys in new format
                speed = line_speeds.get(line.name, line_speeds.get(line.line_id, 0))
                if speed > 0:
                    compatible.append(sku_id)
                    speed_multipliers[sku_id] = speed

            # Update line with derived data
            line.compatible_skus = compatible
            line.sku_speed_multipliers = speed_multipliers
            line.base_speed_units_per_hour = 1.0  # Use multipliers for actual speeds

    # Parse changeover matrices (if omitted, propagate settings.changeover_minutes per line)
    changeover_matrices = []
    for matrix_data in data.get("changeover_matrices", []):
        # Convert string keys to tuples
        minutes = {}
        for key, value in matrix_data.get("changeover_minutes", {}).items():
            # Key format: "SKU-001,SKU-002"
            from_sku, to_sku = key.split(",")
            minutes[(from_sku.strip(), to_sku.strip())] = value

        cost = {}
        for key, value in matrix_data.get("changeover_cost", {}).items():
            from_sku, to_sku = key.split(",")
            cost[(from_sku.strip(), to_sku.strip())] = value

        changeover_matrices.append(ChangeoverMatrix(
            line_id=matrix_data.get("line_id", matrix_data.get("name", "")),
            changeover_minutes=minutes,
            changeover_cost=cost,
            default_minutes=matrix_data.get("default_minutes", default_changeover),
            default_cost=matrix_data.get("default_cost", 100.0),
        ))

    if not changeover_matrices and ("changeover_minutes" in settings or "default_changeover_minutes" in settings):
        for line in lines:
            changeover_matrices.append(
                ChangeoverMatrix(
                    line_id=line.line_id,
                    default_minutes=float(default_changeover),
                    default_cost=100.0,
                )
            )

    # Parse shifts
    shifts = []
    for i, shift_data in enumerate(data.get("shifts", [])):
        start_parts = shift_data["start_time"].split(":")
        end_parts = shift_data["end_time"].split(":")

        # Support both old format (shift_id) and new format (name only)
        shift_id = shift_data.get("shift_id", shift_data.get("name", f"SHIFT-{i+1}"))
        shift_name = shift_data.get("name", shift_id)

        # Get available lines - in new format, use all line IDs if not specified
        available_lines = shift_data.get("available_lines", [])
        if not available_lines:
            # If no available_lines specified, assume all lines are available
            available_lines = [line.line_id for line in lines]
        else:
            # Map line names to IDs if needed
            available_lines = [line_name_to_id.get(ref, ref) for ref in available_lines]

        shifts.append(Shift(
            shift_id=shift_id,
            name=shift_name,
            start_time=time(int(start_parts[0]), int(start_parts[1])),
            end_time=time(int(end_parts[0]), int(end_parts[1])),
            available_lines=available_lines,
            day_of_week=shift_data.get("day_of_week"),
        ))

    # Parse start date
    start_date = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
    if "start_date" in data:
        start_date = datetime.fromisoformat(data["start_date"])

    # Create params
    params = ProductionParams(
        lines=lines,
        skus=skus,
        changeover_matrices=changeover_matrices,
        shifts=shifts,
        planning_horizon_days=data.get("planning_horizon_days", settings.get("planning_horizon_days", 7)),
        start_date=start_date,
        w_makespan=data.get("w_makespan", 1.0),
        w_changeover=data.get("w_changeover", 1.0),
        w_utilization=data.get("w_utilization", 0.5),
        w_priority=data.get("w_priority", 2.0),
    )

    params.validate()
    return params


# ========================================
# JSON Saving
# ========================================

def save_to_json(params: ProductionParams, file_path: str) -> None:
    """
    Save production parameters to a JSON file.

    Args:
        params: Parameters to save
        file_path: Output file path
    """
    data = _params_to_dict(params)

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)


def _params_to_dict(params: ProductionParams) -> dict[str, Any]:
    """Convert ProductionParams to a JSON-serializable dict."""
    data = {
        "planning_horizon_days": params.planning_horizon_days,
        "start_date": params.start_date.isoformat(),
        "w_makespan": params.w_makespan,
        "w_changeover": params.w_changeover,
        "w_utilization": params.w_utilization,
        "w_priority": params.w_priority,
        "lines": [],
        "skus": [],
        "changeover_matrices": [],
        "shifts": [],
    }

    # Lines
    for line in params.lines:
        data["lines"].append({
            "line_id": line.line_id,
            "name": line.name,
            "compatible_skus": line.compatible_skus,
            "base_speed_units_per_hour": line.base_speed_units_per_hour,
            "sku_speed_multipliers": line.sku_speed_multipliers,
            "max_continuous_hours": line.max_continuous_hours,
            "cleaning_time_minutes": line.cleaning_time_minutes,
            "efficiency_percent": line.efficiency_percent,
        })

    # SKUs
    for sku in params.skus:
        sku_dict = {
            "sku_id": sku.sku_id,
            "name": sku.name,
            "demand_units": sku.demand_units,
            "priority": sku.priority,
            "min_batch_size": sku.min_batch_size,
            "starting_stock": sku.starting_stock,
            "underage_buffer_pct": sku.underage_buffer_pct,
            "overage_buffer_pct": sku.overage_buffer_pct,
        }
        if sku.due_date:
            sku_dict["due_date"] = sku.due_date.isoformat()
        data["skus"].append(sku_dict)

    # Changeover matrices
    for matrix in params.changeover_matrices:
        minutes = {f"{k[0]},{k[1]}": v for k, v in matrix.changeover_minutes.items()}
        cost = {f"{k[0]},{k[1]}": v for k, v in matrix.changeover_cost.items()}

        data["changeover_matrices"].append({
            "line_id": matrix.line_id,
            "changeover_minutes": minutes,
            "changeover_cost": cost,
            "default_minutes": matrix.default_minutes,
            "default_cost": matrix.default_cost,
        })

    # Shifts
    for shift in params.shifts:
        shift_dict = {
            "shift_id": shift.shift_id,
            "name": shift.name,
            "start_time": shift.start_time.strftime("%H:%M"),
            "end_time": shift.end_time.strftime("%H:%M"),
            "available_lines": shift.available_lines,
        }
        if shift.day_of_week is not None:
            shift_dict["day_of_week"] = shift.day_of_week
        data["shifts"].append(shift_dict)

    return data


# ========================================
# Solution Saving
# ========================================

def save_solution_json(solution: ScheduleSolution, file_path: str) -> None:
    """
    Save a schedule solution to JSON.

    Args:
        solution: Solution to save
        file_path: Output file path
    """
    data = {
        "makespan_hours": solution.get_makespan_hours(),
        "total_units": solution.get_total_units(),
        "total_changeovers": solution.get_total_changeovers(),
        "line_solutions": [],
    }

    for ls in solution.line_solutions:
        line_data = {
            "line_id": ls.line_id,
            "total_units": ls.get_total_units(),
            "blocks": [],
        }

        for block in ls.production_blocks:
            line_data["blocks"].append({
                "block_id": block.block_id,
                "sku_id": block.sku_id,
                "start_time": block.start_time.isoformat(),
                "end_time": block.end_time.isoformat(),
                "units_produced": block.units_produced,
                "changeover_from": block.changeover_from,
                "changeover_time_minutes": block.changeover_time_minutes,
            })

        data["line_solutions"].append(line_data)

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
