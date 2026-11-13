# Supply Chain Production Scheduling Optimizer

A production scheduling optimization system for manufacturing supply chains.

## Quick Start

### Run from Exe
Double-click `dist/SupplyChainPlanner.exe` to launch the dashboard.

### Run from Python
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Or run the server directly with dashboard
python visualization/server.py
```

## Key Features

- **Genetic Algorithm Optimizer**: Uses GA to find optimal production schedules
- **Flexible Configuration**: Define lines, SKUs, shifts, and speeds via JSON or dashboard  
- **Visual Dashboard**: Interactive Gantt chart and metrics to visualize production plans
- **SKU-Level Speeds**: Define production speeds per SKU per line (0 = incompatible)

## Project Structure

```
supply-chain-planner/
├── main.py              # CLI entry point
├── core/                # Domain logic (params, solution, constraints)
├── optimizer/           # Genetic Algorithm
├── file_io/             # JSON input/output handling
├── visualization/       # Web-based dashboard & server
├── examples/            # Example configurations
├── tests/               # Test suite
└── dist/                # Compiled executable
```

## Configuration Format

```json
{
    "lines": [
        {"name": "Line 1", "efficiency_percent": 91}
    ],
    "skus": [
        {
            "name": "600ml Water",
            "demand_units": 100000,
            "line_speeds": {
                "Line 1": 11520,
                "Line 2": 36000
            }
        }
    ],
    "settings": {
        "planning_horizon_days": 7,
        "changeover_minutes": 120,
        "daily_cleaning_minutes": 60
    }
}
```

## Building the Exe

```bash
python -m PyInstaller --onefile --name SupplyChainPlanner --distpath dist --add-data "visualization;visualization" visualization/server.py
```

## License

MIT
