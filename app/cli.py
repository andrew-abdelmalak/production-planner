"""
cli.py - Headless Command-Line Interface for Production Planner
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from core.config import SCENARIOS, get_scenario
from core.objectives import evaluate_solution, get_demand_fulfillment_pct, print_solution_summary
from file_io.loader import save_solution_json
from file_io.tabular import load_params, save_solution_csv, save_solution_excel
from optimizer.ensemble import EnsembleOptimizer
from optimizer.genetic import GeneticOptimizer


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="production-planner",
        description="Optimize multi-line production schedules from JSON, CSV, or Excel inputs.",
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to a JSON config, Excel (.xlsx) workbook, or directory of CSV templates.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["auto", "json", "csv", "xlsx"],
        default="auto",
        help="Input format (default: auto-detected from path).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output path (.json, .csv, or .xlsx) for the optimized schedule.",
    )
    parser.add_argument(
        "--output-format",
        choices=["auto", "json", "csv", "xlsx"],
        default="auto",
        help="Output file format (default: inferred from --output extension).",
    )
    parser.add_argument(
        "--population",
        type=int,
        default=100,
        help="GA population size (default: 100).",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=None,
        help="GA generations (default: scenario preset or 75).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of independent GA runs (1=single GA, >1=ensemble).",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS.keys()),
        default=None,
        help="Optional weight/iteration preset (balanced, heavy_week, light_week, deadline).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible schedules.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary output.",
    )
    return parser


def _export_solution(solution, output_path: Path, output_format: str) -> None:
    """Export schedule solution to JSON, CSV, or Excel."""
    fmt = output_format.lower()
    if fmt == "auto":
        ext = output_path.suffix.lower()
        if ext == ".csv":
            fmt = "csv"
        elif ext == ".xlsx":
            fmt = "xlsx"
        else:
            fmt = "json"

    if fmt == "json":
        save_solution_json(solution, str(output_path))
    elif fmt == "csv":
        save_solution_csv(solution, output_path)
    elif fmt == "xlsx":
        save_solution_excel(solution, output_path)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.seed is not None:
        random.seed(args.seed)

    params = load_params(args.input, input_format=args.format)

    generations = args.generations
    runs = args.runs
    if args.scenario:
        scenario = get_scenario(args.scenario)
        params.w_makespan = scenario.w_makespan
        params.w_changeover = scenario.w_changeover
        if generations is None:
            generations = scenario.generations
        if runs == 1:
            runs = scenario.ensemble_runs
    if generations is None:
        generations = 75

    if runs > 1:
        optimizer = EnsembleOptimizer(
            params,
            num_runs=runs,
            population_size=args.population,
            generations=generations,
            verbose=not args.quiet,
        )
        solution, _ = optimizer.solve()
    else:
        optimizer = GeneticOptimizer(
            params,
            population_size=args.population,
            generations=generations,
            verbose=False,
        )
        solution = optimizer.solve()

    if args.output:
        _export_solution(solution, Path(args.output), args.output_format)

    eval_summary = evaluate_solution(solution, verbose=False)
    demand_pct = get_demand_fulfillment_pct(solution)

    if not args.quiet:
        print_solution_summary(solution)
        print(f"Overall demand fulfillment: {demand_pct:.1f}%")
        if args.output:
            print(f"Exported schedule to: {args.output}")

    return 0 if eval_summary["feasible"] else 2


if __name__ == "__main__":
    sys.exit(main())
