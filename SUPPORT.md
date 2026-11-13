# Getting help

## Documentation and bugs

Read the root [README](README.md) and the [input format reference](docs/input-format.md) first.

If you encounter a reproducible bug in scheduling constraints, CSV/Excel loading, the CLI, or the desktop GUI, open a report using the [issue forms](https://github.com/andrew-abdelmalak/production-planner/issues/new/choose).

## Security problems

Follow [SECURITY.md](SECURITY.md) to report vulnerabilities privately.

## What is out of scope

- Live ERP, MES, or SCADA database integrations (export/import is file-based via JSON, CSV, and `.xlsx`)
- Exact global optimality guarantees (the solver uses a stochastic genetic algorithm tuned for fast feasible schedules)
- Custom Windows installer code signing or macOS universal notarized bundles
