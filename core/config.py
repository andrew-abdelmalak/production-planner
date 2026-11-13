"""
config.py - Centralized Configuration Constants

All tunable parameters, penalties, and thresholds in one place.
Modify these values to adjust algorithm behavior without hunting through code.
"""

from dataclasses import dataclass

# ========================================
# CHANGEOVER PENALTIES
# ========================================
# Lower = better (0 = free, higher = more penalty)

PENALTY_FRIDAY_CHANGEOVER = 0.0          # Best: Friday/end-of-week (FREE)
PENALTY_START_OF_DAY_CHANGEOVER = 10.0   # Acceptable: Start of day/shift
PENALTY_MID_SHIFT_CHANGEOVER = 100.0     # Worst: Mid-shift (avoid at all costs)

# ========================================
# DEMAND PENALTIES
# ========================================
# Demand < 100% is now a HARD CONSTRAINT (infeasible)
# These penalties are for soft degradation if needed

PENALTY_DEMAND_SHORTFALL_PER_UNIT = 1000.0  # Per unit of unmet demand
PENALTY_INFEASIBLE_SOLUTION = 1e9           # Returned for infeasible solutions

# ========================================
# OBJECTIVE WEIGHTS (Defaults)
# ========================================

DEFAULT_W_MAKESPAN = 1.0
DEFAULT_W_CHANGEOVER = 1.5    # Increased to prioritize fewer changeovers
DEFAULT_W_UTILIZATION = 0.5
DEFAULT_W_PRIORITY = 2.0

# ========================================
# GA DEFAULTS
# ========================================

DEFAULT_POPULATION_SIZE = 100
DEFAULT_GENERATIONS = 75       # Increased from 50 for better convergence
DEFAULT_MUTATION_RATE = 0.15
DEFAULT_CROSSOVER_RATE = 0.80
DEFAULT_TOURNAMENT_SIZE = 3
DEFAULT_ELITISM = 2

# Ensemble optimization
DEFAULT_ENSEMBLE_RUNS = 5

# ========================================
# SCENARIO PRESETS
# ========================================
# Config overrides for specific scenarios

@dataclass
class ScenarioConfig:
    """Configuration preset for a specific scenario."""
    name: str
    generations: int
    ensemble_runs: int
    w_makespan: float
    w_changeover: float
    w_demand: float
    description: str


SCENARIO_BALANCED = ScenarioConfig(
    name="balanced",
    generations=75,
    ensemble_runs=5,
    w_makespan=1.0,
    w_changeover=1.5,
    w_demand=10.0,  # High to ensure demand is met
    description="Default balanced optimization"
)

SCENARIO_HEAVY_WEEK = ScenarioConfig(
    name="heavy_week",
    generations=100,
    ensemble_runs=7,
    w_makespan=0.5,
    w_changeover=0.5,
    w_demand=20.0,  # Prioritize meeting demand
    description="High demand week - focus on meeting all demand"
)

SCENARIO_LIGHT_WEEK = ScenarioConfig(
    name="light_week",
    generations=50,
    ensemble_runs=3,
    w_makespan=1.0,
    w_changeover=3.0,  # Heavily prioritize zero changeovers
    w_demand=5.0,
    description="Low demand week - optimize for zero changeovers"
)

SCENARIO_DEADLINE = ScenarioConfig(
    name="deadline",
    generations=75,
    ensemble_runs=5,
    w_makespan=3.0,  # Prioritize finishing quickly
    w_changeover=0.5,
    w_demand=10.0,
    description="Deadline-critical - minimize total time"
)

SCENARIOS = {
    "balanced": SCENARIO_BALANCED,
    "heavy_week": SCENARIO_HEAVY_WEEK,
    "light_week": SCENARIO_LIGHT_WEEK,
    "deadline": SCENARIO_DEADLINE,
}


def get_scenario(name: str) -> ScenarioConfig:
    """Get a scenario config by name."""
    return SCENARIOS.get(name, SCENARIO_BALANCED)


# ========================================
# CONSTRAINT THRESHOLDS
# ========================================

DEMAND_FULFILLMENT_HARD_CONSTRAINT = 1.00  # 100% required
MIN_BATCH_SIZE_DEFAULT = 100
MAX_CONTINUOUS_HOURS_DEFAULT = 24.0

# Tolerance for floating point comparisons
FLOAT_TOLERANCE = 1e-6

# ========================================
# CHANGEOVER CLASSIFICATION
# ========================================

class ChangeoverType:
    """Enum-like class for changeover types."""
    FRIDAY = "friday"
    START_OF_DAY = "start_of_day"
    START_OF_SHIFT = "start_of_shift"
    MID_SHIFT = "mid_shift"


def get_changeover_penalty(changeover_type: str) -> float:
    """
    Get the penalty for a specific changeover type.

    Args:
        changeover_type: One of ChangeoverType values

    Returns:
        Penalty value (lower = better)
    """
    penalties = {
        ChangeoverType.FRIDAY: PENALTY_FRIDAY_CHANGEOVER,
        ChangeoverType.START_OF_DAY: PENALTY_START_OF_DAY_CHANGEOVER,
        ChangeoverType.START_OF_SHIFT: PENALTY_START_OF_DAY_CHANGEOVER,  # Same as start of day
        ChangeoverType.MID_SHIFT: PENALTY_MID_SHIFT_CHANGEOVER,
    }
    return penalties.get(changeover_type, PENALTY_MID_SHIFT_CHANGEOVER)
