"""
Supply Chain Production Scheduling - Core Package

This package contains the core domain logic for production scheduling optimization.
"""

from .config import (
    PENALTY_FRIDAY_CHANGEOVER,
    PENALTY_MID_SHIFT_CHANGEOVER,
    PENALTY_START_OF_DAY_CHANGEOVER,
    ChangeoverType,
)
from .constraints import validate_solution
from .objectives import (
    classify_changeover,
    get_demand_fulfillment_pct,
    objective_changeover_cost,
    objective_changeover_with_timing,
    objective_demand_penalty,
    objective_makespan,
    objective_weighted,
)
from .params import (
    SKU,
    ChangeoverMatrix,
    ProductionLine,
    ProductionParams,
    Shift,
    make_demo_params,
)
from .solution import (
    LineSolution,
    ProductionBlock,
    ScheduleSolution,
)

__all__ = [
    # Params
    "ProductionLine",
    "SKU",
    "ChangeoverMatrix",
    "Shift",
    "ProductionParams",
    "make_demo_params",
    # Solution
    "ProductionBlock",
    "LineSolution",
    "ScheduleSolution",
    # Constraints
    "validate_solution",
    # Objectives
    "objective_makespan",
    "objective_changeover_cost",
    "objective_demand_penalty",
    "objective_weighted",
    "objective_changeover_with_timing",
    "classify_changeover",
    "get_demand_fulfillment_pct",
    # Config
    "ChangeoverType",
    "PENALTY_FRIDAY_CHANGEOVER",
    "PENALTY_MID_SHIFT_CHANGEOVER",
    "PENALTY_START_OF_DAY_CHANGEOVER",
]

