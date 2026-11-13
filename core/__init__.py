"""
Supply Chain Production Scheduling - Core Package

This package contains the core domain logic for production scheduling optimization.
"""

from .params import (
    ProductionLine,
    SKU,
    ChangeoverMatrix,
    Shift,
    ProductionParams,
    make_demo_params,
)
from .solution import (
    ProductionBlock,
    LineSolution,
    ScheduleSolution,
)
from .constraints import validate_solution
from .objectives import (
    objective_makespan,
    objective_changeover_cost,
    objective_demand_penalty,
    objective_weighted,
    objective_changeover_with_timing,
    classify_changeover,
    get_demand_fulfillment_pct,
)
from .config import (
    ChangeoverType,
    PENALTY_FRIDAY_CHANGEOVER,
    PENALTY_START_OF_DAY_CHANGEOVER,
    PENALTY_MID_SHIFT_CHANGEOVER,
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
]

