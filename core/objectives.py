"""
objectives.py - Objective Functions for Production Scheduling

Defines objective functions for evaluating schedule quality:
- objective_makespan(): Minimize completion time
- objective_changeover_cost(): Minimize changeover costs
- objective_changeover_with_timing(): Penalize by changeover timing (Friday=0, Start=10, Mid=100)
- objective_demand_penalty(): Penalize unmet demand (treated as HARD constraint)
- objective_utilization(): Maximize line utilization
- objective_weighted(): Combined weighted objective with hard demand constraint

This mirrors the objective function structure in the EV project.
"""

from __future__ import annotations
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

# Import centralized configuration
from .config import (
    PENALTY_FRIDAY_CHANGEOVER,
    PENALTY_START_OF_DAY_CHANGEOVER,
    PENALTY_MID_SHIFT_CHANGEOVER,
    PENALTY_INFEASIBLE_SOLUTION,
    DEMAND_FULFILLMENT_HARD_CONSTRAINT,
    ChangeoverType,
    get_changeover_penalty,
)

if TYPE_CHECKING:
    from .solution import ScheduleSolution, ProductionBlock
    from .params import ProductionParams


# ========================================
# PENALTY CONSTANTS
# ========================================

DEMAND_PENALTY_PER_UNIT = 0.1  # Base penalty per unit of unmet demand
PRIORITY_WEIGHT_MAP = {1: 5.0, 2: 3.0, 3: 2.0, 4: 1.5, 5: 1.0}  # Priority -> weight multiplier


# ========================================
# OBJECTIVE 1: Makespan
# ========================================

def objective_makespan(solution: "ScheduleSolution") -> float:
    """
    Calculate the makespan: total time from start to completion.
    
    Objective: MINIMIZE
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        Makespan in hours
    """
    return solution.get_makespan_hours()


def objective_makespan_detailed(solution: "ScheduleSolution") -> Dict:
    """
    Detailed makespan information.
    
    Returns:
        Dictionary with makespan and per-line completion times
    """
    line_completions = {}
    for ls in solution.line_solutions:
        comp = ls.get_completion_time()
        if comp:
            line_completions[ls.line_id] = comp
    
    # Find bottleneck (line that finishes last)
    bottleneck = None
    if line_completions:
        bottleneck = max(line_completions.items(), key=lambda x: x[1])[0]
    
    return {
        "makespan_hours": solution.get_makespan_hours(),
        "line_completions": line_completions,
        "bottleneck_line": bottleneck,
    }


# ========================================
# OBJECTIVE 2: Changeover Cost
# ========================================

def classify_changeover(
    block: "ProductionBlock",
    shifts: list,
    params: "ProductionParams"
) -> str:
    """
    Classify a changeover by its timing.
    
    Returns one of:
    - ChangeoverType.FRIDAY: End of week (Friday) - FREE
    - ChangeoverType.START_OF_DAY: Beginning of a new day - Acceptable
    - ChangeoverType.START_OF_SHIFT: Beginning of a shift - Acceptable
    - ChangeoverType.MID_SHIFT: Middle of a shift - Worst
    
    Args:
        block: The production block that has a changeover at its start
        shifts: List of Shift objects from params
        params: Production parameters
    
    Returns:
        ChangeoverType string constant
    """
    changeover_time = block.start_time
    
    # Check if Friday (weekday 4 = Friday)
    if changeover_time.weekday() == 4:
        return ChangeoverType.FRIDAY
    
    # Check if start of day (within 30 min of first shift start)
    block_time = changeover_time.time()
    for shift in shifts:
        # Calculate minutes from midnight for comparison
        shift_start_mins = shift.start_time.hour * 60 + shift.start_time.minute
        block_mins = block_time.hour * 60 + block_time.minute
        
        # Within 30 minutes of shift start?
        diff = abs(block_mins - shift_start_mins)
        if diff <= 30 or diff >= (24 * 60 - 30):  # Handle midnight wrap
            # Check if this is the first shift of the day
            is_morning_shift = shift.start_time.hour >= 6 and shift.start_time.hour <= 10
            if is_morning_shift:
                return ChangeoverType.START_OF_DAY
            else:
                return ChangeoverType.START_OF_SHIFT
    
    # Default: mid-shift changeover (worst case)
    return ChangeoverType.MID_SHIFT


def objective_changeover_cost(solution: "ScheduleSolution") -> float:
    """
    Calculate total changeover cost across all lines.
    
    Objective: MINIMIZE
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        Total changeover cost units
    """
    total_cost = 0.0
    params = solution.params
    
    for ls in solution.line_solutions:
        sorted_blocks = ls.get_blocks_sorted()
        
        for i in range(len(sorted_blocks) - 1):
            current = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]
            
            # Get changeover cost between these SKUs
            cost = params.get_changeover_cost(
                ls.line_id, current.sku_id, next_block.sku_id
            )
            total_cost += cost
    
    return total_cost


def objective_changeover_with_timing(solution: "ScheduleSolution") -> Tuple[float, Dict[str, int]]:
    """
    Calculate changeover penalty based on TIMING preferences.
    
    Penalty hierarchy:
    - Friday changeovers: FREE (0 penalty)
    - Start of day/shift: Acceptable (10 penalty)
    - Mid-shift: Avoid at all costs (100 penalty)
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        Tuple of (total_penalty, breakdown_dict)
        breakdown_dict has counts: {'friday': N, 'start_of_day': N, 'mid_shift': N}
    """
    total_penalty = 0.0
    breakdown = {
        ChangeoverType.FRIDAY: 0,
        ChangeoverType.START_OF_DAY: 0,
        ChangeoverType.START_OF_SHIFT: 0,
        ChangeoverType.MID_SHIFT: 0,
    }
    
    params = solution.params
    shifts = params.shifts
    
    for ls in solution.line_solutions:
        sorted_blocks = ls.get_blocks_sorted()
        
        for i in range(len(sorted_blocks) - 1):
            current = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]
            
            # Only count if there's actually a changeover (different SKU)
            if current.sku_id != next_block.sku_id:
                changeover_type = classify_changeover(next_block, shifts, params)
                penalty = get_changeover_penalty(changeover_type)
                
                total_penalty += penalty
                breakdown[changeover_type] = breakdown.get(changeover_type, 0) + 1
    
    return total_penalty, breakdown


def objective_changeover_time(solution: "ScheduleSolution") -> float:
    """
    Calculate total changeover time in minutes.
    
    Objective: MINIMIZE
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        Total changeover time in minutes
    """
    return solution.get_total_changeover_time()


def objective_changeover_detailed(solution: "ScheduleSolution") -> Dict:
    """
    Detailed changeover breakdown.
    
    Returns:
        Dictionary with total cost, time, count, and per-line breakdown
    """
    params = solution.params
    
    by_line = {}
    total_cost = 0.0
    total_time = 0.0
    total_count = 0
    
    for ls in solution.line_solutions:
        line_cost = 0.0
        line_time = 0.0
        line_count = 0
        
        sorted_blocks = ls.get_blocks_sorted()
        for i in range(len(sorted_blocks) - 1):
            current = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]
            
            if current.sku_id != next_block.sku_id:
                cost = params.get_changeover_cost(ls.line_id, current.sku_id, next_block.sku_id)
                time = params.get_changeover_time(ls.line_id, current.sku_id, next_block.sku_id)
                
                line_cost += cost
                line_time += time
                line_count += 1
        
        by_line[ls.line_id] = {
            "cost": line_cost,
            "time_minutes": line_time,
            "count": line_count,
        }
        
        total_cost += line_cost
        total_time += line_time
        total_count += line_count
    
    return {
        "total_cost": total_cost,
        "total_time_minutes": total_time,
        "total_count": total_count,
        "by_line": by_line,
    }


# ========================================
# OBJECTIVE 3: Demand Penalty
# ========================================

# ========================================
# OBJECTIVE 3: Demand Penalty & Inventory
# ========================================

def get_produced_counts(solution: "ScheduleSolution") -> Dict[str, int]:
    """Helper to get total produced units per SKU."""
    counts = {}
    for ls in solution.line_solutions:
        line_counts = ls.get_units_by_sku()
        for sku_id, units in line_counts.items():
            counts[sku_id] = counts.get(sku_id, 0) + units
    return counts

def objective_demand_penalty(solution: "ScheduleSolution") -> float:
    """
    Calculate penalty for unmet demand OR overproduction beyond buffer.
    
    Objective: MINIMIZE (0 = all demand met within buffer)
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        Total penalty (shortfall + excess)
    """
    penalty = 0.0
    produced_counts = get_produced_counts(solution)
    
    for sku in solution.params.skus:
        produced = produced_counts.get(sku.sku_id, 0)
        total_inventory = sku.starting_stock + produced
        target = sku.demand_units
        
        # Calculate allowed range
        min_allowed = target * (1.0 - sku.underage_buffer_pct)
        max_allowed = target * (1.0 + sku.overage_buffer_pct)
        
        priority_weight = PRIORITY_WEIGHT_MAP.get(sku.priority, 1.0)
        
        # 1. Check Underproduction (Shortfall)
        if total_inventory < min_allowed:
            shortfall = min_allowed - total_inventory
            # Heavy penalty for missing minimum requirement
            penalty += shortfall * DEMAND_PENALTY_PER_UNIT * priority_weight
            
        # 2. Check Overproduction (Excess)
        elif total_inventory > max_allowed:
            excess = total_inventory - max_allowed
            # Penalty for holding/waste. Typically lower than shortfall, 
            # but user effectively wants a constraint.
            # Using 50% of base penalty seems reasonable to enforce "Inventory Balancing".
            penalty += excess * DEMAND_PENALTY_PER_UNIT * 0.5 * priority_weight

    return penalty


def objective_demand_detailed(solution: "ScheduleSolution") -> Dict:
    """
    Detailed demand fulfillment breakdown with inventory status.
    
    Returns:
        Dictionary with per-SKU fulfillment details
    """
    produced_counts = get_produced_counts(solution)
    details = {}
    
    for sku in solution.params.skus:
        produced = produced_counts.get(sku.sku_id, 0)
        total_inventory = sku.starting_stock + produced
        target = sku.demand_units
        
        min_allowed = target * (1.0 - sku.underage_buffer_pct)
        max_allowed = target * (1.0 + sku.overage_buffer_pct)
        
        status = "OK"
        shortfall = 0.0
        excess = 0.0
        penalty = 0.0
        
        priority_weight = PRIORITY_WEIGHT_MAP.get(sku.priority, 1.0)
        
        if total_inventory < min_allowed:
            status = "UNDER"
            shortfall = min_allowed - total_inventory
            penalty = shortfall * DEMAND_PENALTY_PER_UNIT * priority_weight
        elif total_inventory > max_allowed:
            status = "OVER"
            excess = total_inventory - max_allowed
            penalty = excess * DEMAND_PENALTY_PER_UNIT * 0.5 * priority_weight
            
        # Fulfillment % is based on TARGET (Demand)
        # We cap it for display or show raw? Raw is better.
        # But conceptually, if we start with 50 and target 100, and produce 50, we have 100% inventory fulfillment.
        fulfillment_pct = (total_inventory / target * 100) if target > 0 else 100.0
        
        details[sku.sku_id] = {
            "name": sku.name,
            "demand": target,
            "starting_stock": sku.starting_stock,
            "produced": produced,
            "total_inventory": total_inventory,
            "fulfillment_pct": fulfillment_pct,
            "min_allowed": min_allowed,
            "max_allowed": max_allowed,
            "status": status,
            "shortfall": shortfall,
            "excess": excess,
            "penalty": penalty,
        }
    
    return details


# ========================================
# OBJECTIVE 5: OTIF (On-Time In-Full)
# ========================================

def objective_otif(solution: "ScheduleSolution") -> float:
    """
    Calculate OTIF (On-Time In-Full) percentage.
    
    A SKU is considered OTIF if:
    1. 100% of demand is fulfilled (In-Full)
    2. The last production block completes before due_date (On-Time)
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        OTIF percentage (0-100)
    """
    otif_details = objective_otif_detailed(solution)
    return otif_details["otif_percentage"]


def objective_otif_detailed(solution: "ScheduleSolution") -> Dict:
    """
    Detailed OTIF breakdown per SKU.
    
    Returns:
        Dictionary with per-SKU OTIF status and overall percentage
    """
    fulfillment = solution.get_demand_fulfillment()
    sku_details = {}
    
    total_with_due_date = 0
    total_on_time_in_full = 0
    
    # Get completion times per SKU
    sku_completion_times = {}
    for ls in solution.line_solutions:
        for block in ls.production_blocks:
            if block.sku_id not in sku_completion_times:
                sku_completion_times[block.sku_id] = block.end_time
            else:
                # Track the latest completion time for each SKU
                if block.end_time > sku_completion_times[block.sku_id]:
                    sku_completion_times[block.sku_id] = block.end_time
    
    for sku in solution.params.skus:
        ratio = fulfillment.get(sku.sku_id, 0.0)
        in_full = ratio >= 1.0  # 100% fulfilled
        
        # Check on-time if due_date is set
        completion_time = sku_completion_times.get(sku.sku_id)
        on_time = True  # Assume on-time if no due date
        
        if sku.due_date is not None:
            total_with_due_date += 1
            if completion_time is not None:
                on_time = completion_time <= sku.due_date
            else:
                # No production scheduled = late
                on_time = False
            
            is_otif = in_full and on_time
            if is_otif:
                total_on_time_in_full += 1
        else:
            is_otif = in_full  # No due date = only check In-Full
        
        sku_details[sku.sku_id] = {
            "name": sku.name,
            "demand": sku.demand_units,
            "produced": int(sku.demand_units * ratio),
            "in_full": in_full,
            "due_date": sku.due_date.isoformat() if sku.due_date else None,
            "completion_time": completion_time.isoformat() if completion_time else None,
            "on_time": on_time,
            "is_otif": is_otif,
        }
    
    # Calculate OTIF percentage
    if total_with_due_date > 0:
        otif_pct = (total_on_time_in_full / total_with_due_date) * 100
    else:
        # If no SKUs have due dates, calculate based on In-Full only
        all_in_full = sum(1 for d in sku_details.values() if d["in_full"])
        otif_pct = (all_in_full / len(sku_details)) * 100 if sku_details else 0
    
    return {
        "otif_percentage": otif_pct,
        "total_skus": len(sku_details),
        "skus_with_due_date": total_with_due_date,
        "skus_on_time_in_full": total_on_time_in_full,
        "by_sku": sku_details,
    }


# ========================================
# OBJECTIVE 4: Line Utilization
# ========================================

def objective_utilization(solution: "ScheduleSolution") -> float:
    """
    Calculate negative utilization (to minimize = maximize utilization).
    
    Objective: MINIMIZE (lower = better utilization)
    
    Returns 1 - average_utilization so that minimizing this
    objective maximizes utilization.
    
    Args:
        solution: Complete schedule solution
    
    Returns:
        1 - average_utilization (0 = perfect utilization)
    """
    # Use planning horizon as available time
    horizon_hours = solution.params.planning_horizon_days * 24
    avg_util = solution.get_average_utilization(horizon_hours)
    return 1.0 - avg_util


def objective_utilization_detailed(solution: "ScheduleSolution") -> Dict:
    """
    Detailed utilization breakdown.
    
    Returns:
        Dictionary with per-line utilization
    """
    horizon_hours = solution.params.planning_horizon_days * 24
    utils = solution.get_line_utilizations(horizon_hours)
    
    return {
        "average_utilization_pct": solution.get_average_utilization(horizon_hours) * 100,
        "by_line": {
            line_id: util * 100 for line_id, util in utils.items()
        },
        "available_hours_per_line": horizon_hours,
    }


# ========================================
# COMBINED OBJECTIVE
# ========================================

def get_demand_fulfillment_pct(solution: "ScheduleSolution") -> float:
    """
    Calculate overall demand fulfillment percentage.
    
    Returns:
        Percentage (0-100) of demand fulfilled
    """
    produced_counts = get_produced_counts(solution)
    total_demand = 0
    total_fulfilled = 0
    
    for sku in solution.params.skus:
        produced = produced_counts.get(sku.sku_id, 0)
        total_inventory = sku.starting_stock + produced
        target = sku.demand_units
        
        total_demand += target
        total_fulfilled += min(total_inventory, target)  # Cap at 100% per SKU
    
    if total_demand == 0:
        return 100.0
    return (total_fulfilled / total_demand) * 100.0


def objective_weighted(
    solution: "ScheduleSolution",
    w_makespan: Optional[float] = None,
    w_changeover: Optional[float] = None,
    w_utilization: Optional[float] = None,
    w_priority: Optional[float] = None,
    enforce_demand_hard_constraint: bool = True,
) -> float:
    """
    Calculate weighted combination of all objectives.
    
    HARD CONSTRAINT: If demand < 100%, returns INFINITY (infeasible solution)
    
    Objective = w_makespan * makespan + w_changeover * changeover_timing_penalty
              + w_utilization * (1-utilization) + w_priority * demand_penalty
    
    Args:
        solution: Complete schedule solution
        w_makespan: Weight for makespan (uses params if None)
        w_changeover: Weight for changeover cost (uses params if None)
        w_utilization: Weight for utilization (uses params if None)
        w_priority: Weight for demand penalty (uses params if None)
        enforce_demand_hard_constraint: If True, demand < 100% = INFEASIBLE
    
    Returns:
        Weighted objective value (MINIMIZE)
        Returns PENALTY_INFEASIBLE_SOLUTION if demand not met
    """
    params = solution.params
    
    # ========================================
    # HARD CONSTRAINT: Demand must be 100%
    # ========================================
    if enforce_demand_hard_constraint:
        demand_pct = get_demand_fulfillment_pct(solution)
        if demand_pct < DEMAND_FULFILLMENT_HARD_CONSTRAINT * 100:
            # Return very high penalty - solution is INFEASIBLE
            return PENALTY_INFEASIBLE_SOLUTION
    
    # ========================================
    # Calculate Soft Objectives
    # ========================================
    
    # Use provided weights or fall back to params
    wm = w_makespan if w_makespan is not None else params.w_makespan
    wc = w_changeover if w_changeover is not None else params.w_changeover
    wu = w_utilization if w_utilization is not None else params.w_utilization
    wp = w_priority if w_priority is not None else params.w_priority
    
    # Calculate individual objectives
    makespan = objective_makespan(solution)
    
    # Use timing-aware changeover penalty (Friday=0, Start=10, Mid=100)
    changeover_penalty, _ = objective_changeover_with_timing(solution)
    
    utilization = objective_utilization(solution)
    demand = objective_demand_penalty(solution)
    
    # Combine with weights
    return wm * makespan + wc * changeover_penalty + wu * utilization + wp * demand


# ========================================
# EVALUATION SUMMARY
# ========================================

def evaluate_solution(solution: "ScheduleSolution", verbose: bool = False) -> Dict:
    """
    Comprehensive solution evaluation.
    
    Args:
        solution: Complete schedule solution
        verbose: Include detailed breakdowns
    
    Returns:
        Dictionary with all metrics and objectives
    """
    from .constraints import validate_solution, get_total_soft_penalty
    
    is_feasible, violations = validate_solution(solution, verbose=False)
    
    results = {
        "feasible": is_feasible,
        "num_lines": len(solution.line_solutions),
        "num_blocks": len(solution.get_all_blocks()),
        "total_units": solution.get_total_units(),
        
        # Primary objectives
        "makespan_hours": objective_makespan(solution),
        "changeover_cost": objective_changeover_cost(solution),
        "changeover_time_minutes": objective_changeover_time(solution),
        "demand_penalty": objective_demand_penalty(solution),
        "weighted_objective": objective_weighted(solution),
        
        # Utilization
        "average_utilization_pct": solution.get_average_utilization(
            solution.params.planning_horizon_days * 24
        ) * 100,
        
        # Violations
        "hard_violations": sum(1 for v in violations if v.severity == "hard"),
        "soft_violations": sum(1 for v in violations if v.severity == "soft"),
        "soft_penalty": get_total_soft_penalty(violations),
    }
    
    if verbose:
        results["makespan_details"] = objective_makespan_detailed(solution)
        results["changeover_details"] = objective_changeover_detailed(solution)
        results["demand_details"] = objective_demand_detailed(solution)
        results["utilization_details"] = objective_utilization_detailed(solution)
        results["violations"] = violations
    
    return results


def print_solution_summary(solution: "ScheduleSolution") -> None:
    """
    Print a human-readable summary of the solution.
    """
    results = evaluate_solution(solution, verbose=True)
    
    print("=" * 70)
    print("SCHEDULE SOLUTION EVALUATION")
    print("=" * 70)
    
    feasible_str = "✓ FEASIBLE" if results["feasible"] else "✗ INFEASIBLE"
    print(f"\nFeasibility: {feasible_str}")
    print(f"Production lines: {results['num_lines']}")
    print(f"Production blocks: {results['num_blocks']}")
    print(f"Total units produced: {results['total_units']:,}")
    
    print("\n" + "-" * 70)
    print("PRIMARY OBJECTIVES")
    print("-" * 70)
    print(f"  Makespan:              {results['makespan_hours']:.2f} hours")
    print(f"  Changeover cost:       {results['changeover_cost']:.2f}")
    print(f"  Changeover time:       {results['changeover_time_minutes']:.0f} minutes")
    print(f"  Demand penalty:        {results['demand_penalty']:.2f}")
    print(f"  Weighted objective:    {results['weighted_objective']:.2f}")
    
    print("\n" + "-" * 70)
    print("LINE UTILIZATION")
    print("-" * 70)
    util_details = results.get("utilization_details", {})
    for line_id, util_pct in util_details.get("by_line", {}).items():
        print(f"  {line_id}: {util_pct:.1f}%")
    print(f"  Average: {results['average_utilization_pct']:.1f}%")
    
    print("\n" + "-" * 70)
    print("DEMAND FULFILLMENT")
    print("-" * 70)
    demand_details = results.get("demand_details", {})
    for sku_id, info in demand_details.items():
        status = "✓" if info["fulfillment_pct"] >= 100 else "✗"
        print(f"  {status} {sku_id}: {info['fulfillment_pct']:.1f}% ({info['produced']:,}/{info['demand']:,})")
    
    print("\n" + "=" * 70)
