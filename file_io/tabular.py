"""
tabular.py - Generic CSV and Excel (.xlsx) Input/Output for Production Scheduling

Supports loading ProductionParams from:
- A directory containing CSV files (lines.csv, skus.csv, line_speeds.csv, shifts.csv,
  and optional changeovers.csv, settings.csv)
- An Excel workbook (.xlsx) with sheets: Lines, SKUs, LineSpeeds, Shifts,
  and optional Changeovers, Settings

Also supports exporting ScheduleSolution to CSV and Excel (.xlsx).
"""

from __future__ import annotations

import csv
from datetime import datetime, time
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

from core.objectives import evaluate_solution
from core.params import SKU, ChangeoverMatrix, ProductionLine, ProductionParams, Shift
from core.solution import ScheduleSolution
from file_io.loader import load_from_json

REQUIRED_CSV_FILES = ("lines.csv", "skus.csv", "line_speeds.csv", "shifts.csv")


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    """Parse an optional integer cell/string; empty values return None."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError as exc:
        raise ValueError(f"Expected integer for '{field_name}', got {value!r}") from exc


def _parse_float(value: Any, default: float, field_name: str) -> float:
    """Parse a float cell/string with a fallback for empty values."""
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"Expected number for '{field_name}', got {value!r}") from exc


def _parse_time(value: Any, field_name: str) -> time:
    """Parse HH:MM (or datetime.time from Excel) into a time object."""
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError(f"Expected HH:MM time for '{field_name}', got {value!r}")
    return time(int(parts[0]), int(parts[1]))


def _parse_optional_datetime(value: Any, field_name: str) -> datetime | None:
    """Parse an optional ISO datetime or Excel datetime cell."""
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Expected ISO date/datetime for '{field_name}', got {value!r}") from exc


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV file into normalized lowercase-keyed row dicts."""
    if not path.exists():
        raise FileNotFoundError(f"Required CSV file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        rows: list[dict[str, str]] = []
        for raw in reader:
            cleaned = {
                k.strip(): (v.strip() if v is not None else "")
                for k, v in raw.items()
                if k is not None
            }
            if any(cleaned.values()):
                rows.append(cleaned)
        return rows


def _read_xlsx_rows(workbook: Workbook, sheet_name: str, required: bool = True) -> list[dict[str, Any]]:
    """Read an Excel worksheet into a list of dicts keyed by header row."""
    if sheet_name not in workbook.sheetnames:
        if required:
            raise ValueError(f"Required Excel worksheet '{sheet_name}' not found")
        return []
    sheet = workbook[sheet_name]
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        raw_headers = next(rows_iter)
    except StopIteration:
        return []
    headers = [str(h).strip() if h is not None else "" for h in raw_headers]
    rows: list[dict[str, Any]] = []
    for raw_row in rows_iter:
        if all(cell is None or str(cell).strip() == "" for cell in raw_row):
            continue
        row_dict = {
            headers[idx]: raw_row[idx]
            for idx in range(min(len(headers), len(raw_row)))
            if headers[idx]
        }
        rows.append(row_dict)
    return rows


def _build_params_from_tables(
    lines_rows: list[dict[str, Any]],
    skus_rows: list[dict[str, Any]],
    speeds_rows: list[dict[str, Any]],
    shifts_rows: list[dict[str, Any]],
    changeovers_rows: list[dict[str, Any]],
    settings_rows: list[dict[str, Any]],
) -> ProductionParams:
    """Assemble and validate ProductionParams from parsed tabular records."""
    settings: dict[str, Any] = {}
    for row in settings_rows:
        key = str(row.get("key", "")).strip()
        if key:
            settings[key] = row.get("value")

    default_co_minutes = _parse_float(
        settings.get("default_changeover_minutes"), 60.0, "default_changeover_minutes"
    )
    default_co_cost = _parse_float(
        settings.get("default_changeover_cost"), 100.0, "default_changeover_cost"
    )

    lines: list[ProductionLine] = []
    line_map: dict[str, ProductionLine] = {}
    for row in lines_rows:
        line_id = str(row.get("line_id", "")).strip()
        if not line_id:
            raise ValueError("Each row in Lines must define 'line_id'")
        name = str(row.get("name", line_id)).strip() or line_id
        line = ProductionLine(
            line_id=line_id,
            name=name,
            compatible_skus=[],
            base_speed_units_per_hour=1.0,
            sku_speed_multipliers={},
            max_continuous_hours=_parse_float(
                row.get("max_continuous_hours"), 24.0, "max_continuous_hours"
            ),
            cleaning_time_minutes=_parse_float(
                row.get("cleaning_time_minutes"), 60.0, "cleaning_time_minutes"
            ),
            efficiency_percent=_parse_float(
                row.get("efficiency_percent"), 100.0, "efficiency_percent"
            ),
        )
        lines.append(line)
        line_map[line_id] = line

    skus: list[SKU] = []
    for row in skus_rows:
        sku_id = str(row.get("sku_id", "")).strip()
        if not sku_id:
            raise ValueError("Each row in SKUs must define 'sku_id'")
        name = str(row.get("name", sku_id)).strip() or sku_id
        demand_raw = _parse_optional_int(row.get("demand_units"), "demand_units")
        if demand_raw is None:
            raise ValueError(f"SKU '{sku_id}' is missing 'demand_units'")
        priority_val = _parse_optional_int(row.get("priority"), "priority")
        min_batch_val = _parse_optional_int(row.get("min_batch_size"), "min_batch_size")
        starting_stock_val = _parse_optional_int(row.get("starting_stock"), "starting_stock")
        skus.append(
            SKU(
                sku_id=sku_id,
                name=name,
                demand_units=demand_raw,
                priority=5 if priority_val is None else priority_val,
                due_date=_parse_optional_datetime(row.get("due_date"), "due_date"),
                min_batch_size=100 if min_batch_val is None else min_batch_val,
                starting_stock=0 if starting_stock_val is None else starting_stock_val,
                underage_buffer_pct=_parse_float(
                    row.get("underage_buffer_pct"), 0.0, "underage_buffer_pct"
                ),
                overage_buffer_pct=_parse_float(
                    row.get("overage_buffer_pct"), 0.0, "overage_buffer_pct"
                ),
            )
        )

    for row in speeds_rows:
        sku_id = str(row.get("sku_id", "")).strip()
        line_id = str(row.get("line_id", "")).strip()
        speed = _parse_float(row.get("units_per_hour"), 0.0, "units_per_hour")
        if line_id not in line_map:
            raise ValueError(f"LineSpeeds references unknown line_id '{line_id}'")
        if speed > 0:
            line = line_map[line_id]
            if sku_id not in line.compatible_skus:
                line.compatible_skus.append(sku_id)
            line.sku_speed_multipliers[sku_id] = speed

    shifts: list[Shift] = []
    all_line_ids = [line.line_id for line in lines]
    for idx, row in enumerate(shifts_rows):
        shift_id = str(row.get("shift_id", f"SHIFT-{idx + 1}")).strip() or f"SHIFT-{idx + 1}"
        shift_name = str(row.get("name", shift_id)).strip() or shift_id
        avail_raw = str(row.get("available_lines", "") or "").strip()
        if avail_raw:
            available_lines = [part.strip() for part in avail_raw.split(";") if part.strip()]
        else:
            available_lines = list(all_line_ids)
        shifts.append(
            Shift(
                shift_id=shift_id,
                name=shift_name,
                start_time=_parse_time(row.get("start_time"), "start_time"),
                end_time=_parse_time(row.get("end_time"), "end_time"),
                available_lines=available_lines,
                day_of_week=_parse_optional_int(row.get("day_of_week"), "day_of_week"),
            )
        )

    matrices_by_line: dict[str, ChangeoverMatrix] = {
        line.line_id: ChangeoverMatrix(
            line_id=line.line_id,
            default_minutes=default_co_minutes,
            default_cost=default_co_cost,
        )
        for line in lines
    }
    for row in changeovers_rows:
        line_id = str(row.get("line_id", "")).strip()
        from_sku = str(row.get("from_sku", "")).strip()
        to_sku = str(row.get("to_sku", "")).strip()
        if line_id not in matrices_by_line:
            raise ValueError(f"Changeovers references unknown line_id '{line_id}'")
        matrix = matrices_by_line[line_id]
        if from_sku and to_sku:
            if row.get("changeover_minutes") not in (None, ""):
                matrix.changeover_minutes[(from_sku, to_sku)] = _parse_float(
                    row.get("changeover_minutes"), default_co_minutes, "changeover_minutes"
                )
            if row.get("changeover_cost") not in (None, ""):
                matrix.changeover_cost[(from_sku, to_sku)] = _parse_float(
                    row.get("changeover_cost"), default_co_cost, "changeover_cost"
                )

    start_date = _parse_optional_datetime(settings.get("start_date"), "start_date")
    if start_date is None:
        start_date = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)

    params = ProductionParams(
        lines=lines,
        skus=skus,
        changeover_matrices=list(matrices_by_line.values()),
        shifts=shifts,
        planning_horizon_days=_parse_optional_int(
            settings.get("planning_horizon_days"), "planning_horizon_days"
        )
        or 7,
        start_date=start_date,
        w_makespan=_parse_float(settings.get("w_makespan"), 1.0, "w_makespan"),
        w_changeover=_parse_float(settings.get("w_changeover"), 1.0, "w_changeover"),
        w_utilization=_parse_float(settings.get("w_utilization"), 0.5, "w_utilization"),
        w_priority=_parse_float(settings.get("w_priority"), 2.0, "w_priority"),
    )
    params.validate()
    return params


def load_from_csv_dir(directory: str | Path) -> ProductionParams:
    """Load ProductionParams from a directory of factory CSV files."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"CSV template directory not found: {directory}")

    lines_rows = _read_csv_rows(dir_path / "lines.csv")
    skus_rows = _read_csv_rows(dir_path / "skus.csv")
    speeds_rows = _read_csv_rows(dir_path / "line_speeds.csv")
    shifts_rows = _read_csv_rows(dir_path / "shifts.csv")
    changeovers_rows = (
        _read_csv_rows(dir_path / "changeovers.csv")
        if (dir_path / "changeovers.csv").exists()
        else []
    )
    settings_rows = (
        _read_csv_rows(dir_path / "settings.csv")
        if (dir_path / "settings.csv").exists()
        else []
    )
    return _build_params_from_tables(
        lines_rows, skus_rows, speeds_rows, shifts_rows, changeovers_rows, settings_rows
    )


def load_from_excel(file_path: str | Path) -> ProductionParams:
    """Load ProductionParams from an Excel (.xlsx) workbook."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel workbook not found: {file_path}")
    wb = load_workbook(path, data_only=True)
    try:
        return _build_params_from_tables(
            _read_xlsx_rows(wb, "Lines", required=True),
            _read_xlsx_rows(wb, "SKUs", required=True),
            _read_xlsx_rows(wb, "LineSpeeds", required=True),
            _read_xlsx_rows(wb, "Shifts", required=True),
            _read_xlsx_rows(wb, "Changeovers", required=False),
            _read_xlsx_rows(wb, "Settings", required=False),
        )
    finally:
        wb.close()


def load_params(source: str | Path, input_format: str = "auto") -> ProductionParams:
    """Load ProductionParams from JSON, Excel (.xlsx), or a CSV directory."""
    path = Path(source)
    fmt = input_format.lower()
    if fmt == "auto":
        if path.is_dir():
            fmt = "csv"
        elif path.suffix.lower() == ".csv":
            path = path.parent
            fmt = "csv"
        elif path.suffix.lower() == ".xlsx":
            fmt = "xlsx"
        elif path.suffix.lower() == ".json":
            fmt = "json"
        else:
            raise ValueError(f"Cannot infer input format for '{source}'; pass --format")

    if fmt == "json":
        return load_from_json(str(path))
    if fmt == "csv":
        return load_from_csv_dir(path)
    if fmt == "xlsx":
        return load_from_excel(path)
    raise ValueError(f"Unsupported input format: {input_format}")


def _serialize_tables(params: ProductionParams) -> list[tuple[str, str, list[str], list[list]]]:
    """Build normalized tabular representations shared by Excel and CSV exports."""
    default_co_min = (
        params.changeover_matrices[0].default_minutes if params.changeover_matrices else 60.0
    )
    default_co_cost = (
        params.changeover_matrices[0].default_cost if params.changeover_matrices else 100.0
    )
    return [
        (
            "Settings",
            "settings.csv",
            ["key", "value"],
            [
                ["start_date", params.start_date.isoformat()],
                ["planning_horizon_days", params.planning_horizon_days],
                ["default_changeover_minutes", default_co_min],
                ["default_changeover_cost", default_co_cost],
                ["w_makespan", params.w_makespan],
                ["w_changeover", params.w_changeover],
                ["w_utilization", params.w_utilization],
                ["w_priority", params.w_priority],
            ],
        ),
        (
            "Lines",
            "lines.csv",
            ["line_id", "name", "efficiency_percent", "max_continuous_hours", "cleaning_time_minutes"],
            [
                [
                    line.line_id,
                    line.name,
                    line.efficiency_percent,
                    line.max_continuous_hours,
                    line.cleaning_time_minutes,
                ]
                for line in params.lines
            ],
        ),
        (
            "SKUs",
            "skus.csv",
            [
                "sku_id",
                "name",
                "demand_units",
                "priority",
                "min_batch_size",
                "starting_stock",
                "due_date",
                "underage_buffer_pct",
                "overage_buffer_pct",
            ],
            [
                [
                    sku.sku_id,
                    sku.name,
                    sku.demand_units,
                    sku.priority,
                    sku.min_batch_size,
                    sku.starting_stock,
                    sku.due_date.isoformat() if sku.due_date else "",
                    sku.underage_buffer_pct,
                    sku.overage_buffer_pct,
                ]
                for sku in params.skus
            ],
        ),
        (
            "LineSpeeds",
            "line_speeds.csv",
            ["sku_id", "line_id", "units_per_hour"],
            [
                [
                    sku_id,
                    line.line_id,
                    line.base_speed_units_per_hour * line.sku_speed_multipliers.get(sku_id, 1.0),
                ]
                for line in params.lines
                for sku_id in line.compatible_skus
            ],
        ),
        (
            "Shifts",
            "shifts.csv",
            ["shift_id", "name", "start_time", "end_time", "day_of_week", "available_lines"],
            [
                [
                    shift.shift_id,
                    shift.name,
                    shift.start_time.strftime("%H:%M"),
                    shift.end_time.strftime("%H:%M"),
                    "" if shift.day_of_week is None else shift.day_of_week,
                    ";".join(shift.available_lines),
                ]
                for shift in params.shifts
            ],
        ),
        (
            "Changeovers",
            "changeovers.csv",
            ["line_id", "from_sku", "to_sku", "changeover_minutes", "changeover_cost"],
            [
                [
                    matrix.line_id,
                    pair[0],
                    pair[1],
                    matrix.changeover_minutes.get(pair, matrix.default_minutes),
                    matrix.changeover_cost.get(pair, matrix.default_cost),
                ]
                for matrix in params.changeover_matrices
                for pair in sorted(set(matrix.changeover_minutes.keys()) | set(matrix.changeover_cost.keys()))
            ],
        ),
    ]


def save_to_excel(params: ProductionParams, file_path: str | Path) -> None:
    """Export ProductionParams to a formatted Excel (.xlsx) workbook."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    tables = _serialize_tables(params)

    for index, (sheet_name, _, headers, rows) in enumerate(tables):
        ws = wb.active if index == 0 else wb.create_sheet(sheet_name)
        ws.title = sheet_name
        ws.append(headers)
        for row in rows:
            ws.append(row)

    wb.save(path)


def save_to_csv_dir(params: ProductionParams, directory: str | Path) -> None:
    """Export ProductionParams to a directory of CSV files."""
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    for _, filename, headers, rows in _serialize_tables(params):
        with (dir_path / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)


def save_solution_csv(solution: ScheduleSolution, file_path: str | Path) -> None:
    """Export scheduled production blocks to a flat CSV file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sku_names = {sku.sku_id: sku.name for sku in solution.params.skus}

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "block_id",
            "line_id",
            "sku_id",
            "sku_name",
            "start_time",
            "end_time",
            "duration_hours",
            "units_produced",
            "changeover_from",
            "changeover_time_minutes",
        ])
        for block in solution.get_all_blocks_sorted():
            writer.writerow([
                block.block_id,
                block.line_id,
                block.sku_id,
                sku_names.get(block.sku_id, block.sku_id),
                block.start_time.isoformat(),
                block.end_time.isoformat(),
                round(block.get_duration_hours(), 4),
                block.units_produced,
                block.changeover_from or "",
                round(block.changeover_time_minutes, 2),
            ])


def save_solution_excel(solution: ScheduleSolution, file_path: str | Path) -> None:
    """Export a schedule solution (Summary, Schedule, Fulfillment) to Excel (.xlsx)."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    eval_data = evaluate_solution(solution, verbose=True)

    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["metric", "value"])
    for key in (
        "feasible",
        "num_lines",
        "num_blocks",
        "total_units",
        "makespan_hours",
        "changeover_cost",
        "changeover_time_minutes",
        "average_utilization_pct",
        "hard_violations",
        "soft_violations",
    ):
        ws_sum.append([key, eval_data[key]])

    ws_sched = wb.create_sheet("Schedule")
    ws_sched.append([
        "block_id",
        "line_id",
        "sku_id",
        "sku_name",
        "start_time",
        "end_time",
        "duration_hours",
        "units_produced",
        "changeover_from",
        "changeover_time_minutes",
    ])
    sku_names = {sku.sku_id: sku.name for sku in solution.params.skus}
    for block in solution.get_all_blocks_sorted():
        ws_sched.append([
            block.block_id,
            block.line_id,
            block.sku_id,
            sku_names.get(block.sku_id, block.sku_id),
            block.start_time.isoformat(),
            block.end_time.isoformat(),
            round(block.get_duration_hours(), 4),
            block.units_produced,
            block.changeover_from or "",
            round(block.changeover_time_minutes, 2),
        ])

    ws_ful = wb.create_sheet("Fulfillment")
    ws_ful.append([
        "sku_id",
        "name",
        "demand",
        "starting_stock",
        "produced",
        "total_inventory",
        "fulfillment_pct",
        "status",
    ])
    for sku_id, info in eval_data.get("demand_details", {}).items():
        ws_ful.append([
            sku_id,
            info["name"],
            info["demand"],
            info["starting_stock"],
            info["produced"],
            info["total_inventory"],
            round(info["fulfillment_pct"], 2),
            info["status"],
        ])

    wb.save(path)
