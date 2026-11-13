# Contributing to production-planner

Bug reports, constraint or optimizer fixes, input-format improvements, and documentation updates are welcome. For larger changes, open an issue first to discuss the design.

## Before you start

- Search [existing issues](https://github.com/andrew-abdelmalak/production-planner/issues) to avoid duplicates.
- Open an issue before changing hard constraint rules, fitness weighting, or the CSV/Excel table schema.
- By participating, you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Set up your environment

Requirements: Python 3.11+ with `uv`. The `gui` extra installs PySide6 for the desktop Gantt interface; omit `--extra gui` for headless CLI development only.

```bash
git clone https://github.com/andrew-abdelmalak/production-planner.git
cd production-planner
uv sync --locked --extra gui
```

## Run the checks

```bash
uv run ruff check .
QT_QPA_PLATFORM=offscreen uv run pytest -v
uv run production-planner -i examples/water_factory_config.json --population 30 --generations 20 --seed 42
uv run production-planner -i templates/factory_template.xlsx --population 20 --generations 15 --seed 42
```

CI runs Ruff linting, the full `pytest` suite under offscreen Qt, and CLI smoke checks on every push and pull request. Pull requests with failing checks cannot be merged.

## Make your change

1. Create a branch from `main`: `git switch -c fix/short-description`.
2. Keep each pull request focused on a single topic.
3. Add or update unit tests in `tests/` when changing scheduling constraints, loader behavior, or CLI options.
4. Keep [docs/input-format.md](docs/input-format.md) and [README.md](README.md) consistent with code changes.
5. Never commit proprietary factory names, customer orders, or confidential company datasets.

## Commit messages

Use a concise imperative summary under 72 characters (for example, `fix: handle overnight shift crossing midnight`).

## Open a pull request

Fill out the checklist in the pull request template and verify that CI passes before requesting review.
