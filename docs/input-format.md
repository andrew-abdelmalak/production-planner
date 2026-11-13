# Factory Input Formats

You can configure `production-planner` using any of three equivalent input formats:

1. **JSON file** (such as `examples/small_factory.json` or `examples/water_factory_config.json`)
2. **Excel workbook (`.xlsx`)** (template: `templates/factory_template.xlsx`)
3. **Directory of CSV files** (template folder: `templates/`)

All three formats map directly to `core.params.ProductionParams` and produce identical schedules when loaded and solved with the same random seed.

## Quick Conversion Between Formats

Use `file_io.tabular` to convert an existing JSON config to Excel or CSV before editing:

```bash
uv run python -c "from file_io.tabular import load_params, save_to_excel, save_to_csv_dir; p = load_params('examples/small_factory.json'); save_to_excel(p, 'my_factory.xlsx'); save_to_csv_dir(p, 'my_factory_csv')"
```

Run the optimizer on any format from the command line:

```bash
uv run production-planner -i templates/factory_template.xlsx -o outputs/schedule.xlsx --seed 42
uv run production-planner -i templates/ -o outputs/schedule.csv --seed 42
```

## Excel (`.xlsx`) and CSV Directory Schema

Each Excel worksheet corresponds one-to-one with a CSV file in a directory:

| Excel Sheet | CSV Filename | Required | Purpose |
| :--- | :--- | :--- | :--- |
| `Lines` | `lines.csv` | Yes | Production lines, line efficiency, and cleaning stops |
| `SKUs` | `skus.csv` | Yes | Products, target demands, priorities, and stock buffers |
| `LineSpeeds` | `line_speeds.csv` | Yes | Compatible `(sku_id, line_id)` pairs and nominal speeds |
| `Shifts` | `shifts.csv` | Yes | Working shifts and overnight/weekday availability |
| `Changeovers` | `changeovers.csv` | No | Pairwise SKU-to-SKU changeover durations and costs |
| `Settings` | `settings.csv` | No | Planning horizon, start timestamp, default changeovers, objective weights |

### `Lines` / `lines.csv`

| Column | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `line_id` | string | Required | Unique identifier (e.g. `LINE-A`) |
| `name` | string | `line_id` | Display name |
| `efficiency_percent` | float | `100.0` | Effective OEE/speed multiplier (`85.0` means 85% of nominal speed) |
| `max_continuous_hours` | float | `24.0` | Maximum run length before a mandatory cleaning stop |
| `cleaning_time_minutes` | float | `60.0` | Duration of each mandatory cleaning stop in minutes |

### `SKUs` / `skus.csv`

| Column | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sku_id` | string | Required | Unique product code (e.g. `SKU-001`) |
| `name` | string | `sku_id` | Human-readable product name |
| `demand_units` | int | Required | Target production volume over the horizon |
| `priority` | int | `5` | Priority rank (`1` = highest priority) |
| `min_batch_size` | int | `100` | Minimum continuous batch size in units |
| `starting_stock` | int | `0` | Initial on-hand stock before horizon start |
| `due_date` | ISO datetime | empty | Optional due timestamp (`YYYY-MM-DDTHH:MM:SS`) |
| `underage_buffer_pct` | float | `0.0` | Allowable under-production tolerance (%) |
| `overage_buffer_pct` | float | `0.0` | Allowable over-production tolerance (%) |

### `LineSpeeds` / `line_speeds.csv`

Each row defines a valid SKU-on-line assignment (`units_per_hour > 0`). Rows with `units_per_hour <= 0` are treated as incompatible.

| Column | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `sku_id` | string | Yes | References `SKUs.sku_id` |
| `line_id` | string | Yes | References `Lines.line_id` |
| `units_per_hour` | float | Yes | Nominal throughput before line `efficiency_percent` scaling |

### `Shifts` / `shifts.csv`

| Column | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `shift_id` | string | `SHIFT-N` | Unique shift identifier |
| `name` | string | `shift_id` | Shift label |
| `start_time` | `HH:MM` | Required | Shift start time (24-hour clock) |
| `end_time` | `HH:MM` | Required | Shift end time; `end_time <= start_time` indicates an overnight shift crossing midnight |
| `day_of_week` | int or empty | empty (every day) | Optional day index: `0` = Sunday, `1` = Monday, ..., `6` = Saturday |
| `available_lines` | semicolon-separated IDs | all lines | Lines active in this shift (e.g. `LINE-A;LINE-B`) |

### `Changeovers` / `changeovers.csv`

Optional. If omitted, transitions between different SKUs use `default_changeover_minutes` and `default_changeover_cost` from `Settings`, while running the same SKU twice has zero changeover.

| Column | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `line_id` | string | Required | References `Lines.line_id` |
| `from_sku` | string | Required | Preceding SKU ID |
| `to_sku` | string | Required | Following SKU ID |
| `changeover_minutes` | float | `default_changeover_minutes` | Setup duration in minutes |
| `changeover_cost` | float | `default_changeover_cost` | Setup cost |

### `Settings` / `settings.csv`

Key-value table with columns `key` and `value`:

| Key | Default | Description |
| :--- | :--- | :--- |
| `start_date` | today at `06:00:00` | ISO timestamp for schedule hour `0.0` (e.g. `2026-01-25T06:00:00`) |
| `planning_horizon_days` | `7` | Total schedule window in days |
| `default_changeover_minutes` | `60.0` | Fallback changeover duration between distinct SKUs |
| `default_changeover_cost` | `100.0` | Fallback changeover cost between distinct SKUs |
| `w_makespan` | `1.0` | Objective weight for makespan |
| `w_changeover` | `1.0` | Objective weight for changeover cost/count |
| `w_utilization` | `0.5` | Objective weight for line utilization |
| `w_priority` | `2.0` | Objective weight for priority fulfillment |

## Output Formats

Passing `-o <path>` to `production-planner` supports three extensions:

- `.json`: Full solution metadata, KPI summary, and scheduled blocks (`save_solution_json`)
- `.csv`: Flat production schedule table with block timestamps, quantities, changeovers, and cleaning durations (`save_solution_csv`)
- `.xlsx`: Multi-sheet Excel workbook with `Summary`, `Schedule`, and `Fulfillment` tabs (`save_solution_excel`)
