"""
constraints.py - Constraint Validation System

Defines hard and soft constraints for production scheduling:
- Hard Constraints: Must be satisfied for feasibility
- Soft Constraints: Optimization targets (penalized if violated)

This mirrors the comprehensive constraint checking in the EV project's
FleetSolution.is_feasible() method.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .solution import ScheduleSolution


# ========================================
# Constraint Violation Result
# ========================================

@dataclass
class ConstraintViolation:
    """
    Details about a constraint violation.

    Attributes:
        constraint_name: Name of the violated constraint
        severity: "hard" (infeasible) or "soft" (penalty)
        message: Human-readable description
        location: Where the violation occurred (line, block, etc.)
        penalty: Numeric penalty for soft constraints
    """
    constraint_name: str
    severity: str  # "hard" or "soft"
    message: str
    location: str = ""
    penalty: float = 0.0


# ========================================
# Constraint Checking Functions
# ========================================

def check_line_compatibility(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: SKUs can only run on compatible lines.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for ls in solution.line_solutions:
        line = solution.params.get_line(ls.line_id)

        for block in ls.production_blocks:
            if not line.can_produce(block.sku_id):
                msg = f"SKU '{block.sku_id}' cannot run on line '{ls.line_id}'"
                violation = ConstraintViolation(
                    constraint_name="line_compatibility",
                    severity="hard",
                    message=msg,
                    location=f"Block {block.block_id}",
                )
                violations.append(violation)
                if verbose:
                    print(f"❌ {msg}")

    return violations


def check_no_overlap(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: Production blocks on same line cannot overlap.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for ls in solution.line_solutions:
        sorted_blocks = ls.get_blocks_sorted()

        for i in range(len(sorted_blocks) - 1):
            current = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]

            if current.end_time > next_block.start_time:
                overlap_minutes = (current.end_time - next_block.start_time).total_seconds() / 60
                msg = (f"Blocks overlap on {ls.line_id}: "
                       f"'{current.block_id}' ends at {current.end_time.strftime('%H:%M')}, "
                       f"'{next_block.block_id}' starts at {next_block.start_time.strftime('%H:%M')} "
                       f"({overlap_minutes:.1f} min overlap)")

                violation = ConstraintViolation(
                    constraint_name="no_overlap",
                    severity="hard",
                    message=msg,
                    location=f"Line {ls.line_id}",
                )
                violations.append(violation)
                if verbose:
                    print(f"❌ {msg}")

    return violations


def check_changeover_time(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: Sufficient time between blocks for changeover.

    If a block follows another with different SKU, there must be
    enough time for the changeover.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for ls in solution.line_solutions:
        sorted_blocks = ls.get_blocks_sorted()

        for i in range(len(sorted_blocks) - 1):
            current = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]

            # Get required changeover time
            required_time = solution.params.get_changeover_time(
                ls.line_id, current.sku_id, next_block.sku_id
            )

            # Calculate actual gap
            gap_minutes = (next_block.start_time - current.end_time).total_seconds() / 60

            # Check if changeover time in next block is sufficient
            if next_block.changeover_from == current.sku_id:
                # Changeover accounted for in block
                if next_block.changeover_time_minutes < required_time - 0.1:
                    msg = (f"Insufficient changeover time on {ls.line_id}: "
                           f"need {required_time:.0f}min, have {next_block.changeover_time_minutes:.0f}min "
                           f"for {current.sku_id}→{next_block.sku_id}")

                    violation = ConstraintViolation(
                        constraint_name="changeover_time",
                        severity="hard",
                        message=msg,
                        location=f"Block {next_block.block_id}",
                    )
                    violations.append(violation)
                    if verbose:
                        print(f"❌ {msg}")
            elif gap_minutes < required_time - 0.1:
                # Changeover should be in gap, but gap too small
                msg = (f"No time for changeover on {ls.line_id}: "
                       f"need {required_time:.0f}min gap, have {gap_minutes:.0f}min "
                       f"between blocks {current.block_id} and {next_block.block_id}")

                violation = ConstraintViolation(
                    constraint_name="changeover_time",
                    severity="hard",
                    message=msg,
                    location=f"Line {ls.line_id}",
                )
                violations.append(violation)
                if verbose:
                    print(f"❌ {msg}")

    return violations


def check_min_batch_size(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: Production runs must meet minimum batch size.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for block in solution.get_all_blocks():
        sku = solution.params.get_sku(block.sku_id)

        if block.units_produced < sku.min_batch_size:
            msg = (f"Block {block.block_id} produces {block.units_produced} units "
                   f"of {sku.sku_id}, below minimum batch size of {sku.min_batch_size}")

            violation = ConstraintViolation(
                constraint_name="min_batch_size",
                severity="hard",
                message=msg,
                location=f"Block {block.block_id}",
            )
            violations.append(violation)
            if verbose:
                print(f"❌ {msg}")

    return violations


def check_non_negative(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: All quantities must be non-negative.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for block in solution.get_all_blocks():
        if block.units_produced < 0:
            msg = f"Block {block.block_id} has negative units: {block.units_produced}"
            violation = ConstraintViolation(
                constraint_name="non_negative",
                severity="hard",
                message=msg,
                location=f"Block {block.block_id}",
            )
            violations.append(violation)
            if verbose:
                print(f"❌ {msg}")

        if block.changeover_time_minutes < 0:
            msg = f"Block {block.block_id} has negative changeover: {block.changeover_time_minutes}"
            violation = ConstraintViolation(
                constraint_name="non_negative",
                severity="hard",
                message=msg,
                location=f"Block {block.block_id}",
            )
            violations.append(violation)
            if verbose:
                print(f"❌ {msg}")

    return violations


def check_time_ordering(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: Block end time must be after start time.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for block in solution.get_all_blocks():
        if block.end_time < block.start_time:
            msg = (f"Block {block.block_id} has invalid times: "
                   f"start={block.start_time}, end={block.end_time}")

            violation = ConstraintViolation(
                constraint_name="time_ordering",
                severity="hard",
                message=msg,
                location=f"Block {block.block_id}",
            )
            violations.append(violation)
            if verbose:
                print(f"❌ {msg}")

    return violations


def check_horizon_limit(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: Blocks must end within planning horizon.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    # Calculate absolute horizon end time
    horizon_days = solution.params.planning_horizon_days
    horizon_end = solution.params.start_date + timedelta(days=horizon_days)

    for block in solution.get_all_blocks():
        if block.end_time > horizon_end:
            msg = (f"Block {block.block_id} ends at {block.end_time}, "
                   f"outside planning horizon of {horizon_days} days ({horizon_end})")

            violation = ConstraintViolation(
                constraint_name="horizon_limit",
                severity="hard",
                message=msg,
                location=f"Block {block.block_id}",
            )
            violations.append(violation)
            if verbose:
                print(f"❌ {msg}")

    return violations


def check_max_continuous_run(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    HARD CONSTRAINT: Production blocks must not exceed max run length.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations (empty if constraint satisfied)
    """
    violations = []

    for ls in solution.line_solutions:
        line = solution.params.get_line(ls.line_id)
        if not line.max_continuous_hours or line.max_continuous_hours <= 0:
            continue

        for block in ls.production_blocks:
            duration = block.get_production_hours()
            # Allow small float tolerance
            if duration > line.max_continuous_hours + 0.01:
                msg = (f"Block {block.block_id} duration {duration:.2f}h exceeds "
                       f"max limit {line.max_continuous_hours}h on line {ls.line_id}")

                violation = ConstraintViolation(
                    constraint_name="max_continuous_run",
                    severity="hard",
                    message=msg,
                    location=f"Block {block.block_id}",
                )
                violations.append(violation)
                if verbose:
                    print(f"❌ {msg}")

    return violations


# ========================================
# Soft Constraint Checking
# ========================================

def check_demand_fulfillment(
    solution: ScheduleSolution,
    verbose: bool = False
) -> list[ConstraintViolation]:
    """
    SOFT CONSTRAINT: All SKU demands should be met.

    Generates a penalty for each unit of unmet demand.

    Args:
        solution: Schedule to check
        verbose: Print violations to console

    Returns:
        List of violations with penalties
    """
    violations = []
    fulfillment = solution.get_demand_fulfillment()

    for sku in solution.params.skus:
        ratio = fulfillment.get(sku.sku_id, 0.0)

        if ratio < 1.0:
            shortfall = int(sku.demand_units * (1.0 - ratio))
            # Penalty proportional to priority (higher priority = higher penalty)
            penalty = shortfall * (6 - sku.priority)  # Priority 1 → weight 5, priority 5 → weight 1

            msg = (f"SKU {sku.sku_id} demand not fully met: "
                   f"{ratio*100:.1f}% fulfilled, {shortfall:,} units short")

            violation = ConstraintViolation(
                constraint_name="demand_fulfillment",
                severity="soft",
                message=msg,
                location=f"SKU {sku.sku_id}",
                penalty=penalty,
            )
            violations.append(violation)
            if verbose:
                print(f"⚠️ {msg} (penalty: {penalty:.0f})")

    return violations


# ========================================
# Main Validation Function
# ========================================

def validate_solution(
    solution: ScheduleSolution,
    verbose: bool = False
) -> tuple[bool, list[ConstraintViolation]]:
    """
    Comprehensive solution validation.

    Checks all hard and soft constraints and returns results.

    Args:
        solution: Schedule to validate
        verbose: Print all violations to console

    Returns:
        Tuple of (is_feasible, violations)
        is_feasible is True only if no HARD constraints violated
    """
    all_violations = []

    # Check all hard constraints
    hard_checks = [
        check_line_compatibility,
        check_no_overlap,
        check_changeover_time,
        check_min_batch_size,
        check_max_continuous_run,
        check_horizon_limit,
        check_non_negative,
        check_time_ordering,
    ]

    for check_fn in hard_checks:
        violations = check_fn(solution, verbose)
        all_violations.extend(violations)

    # Check soft constraints
    soft_checks = [
        check_demand_fulfillment,
    ]

    for check_fn in soft_checks:
        violations = check_fn(solution, verbose)
        all_violations.extend(violations)

    # Solution is feasible only if no hard constraints violated
    hard_violations = [v for v in all_violations if v.severity == "hard"]
    is_feasible = len(hard_violations) == 0

    if verbose:
        print()
        if is_feasible:
            print("✓ Solution is FEASIBLE")
        else:
            print(f"✗ Solution is INFEASIBLE ({len(hard_violations)} hard constraint violations)")

        soft_violations = [v for v in all_violations if v.severity == "soft"]
        if soft_violations:
            total_penalty = sum(v.penalty for v in soft_violations)
            print(f"⚠️ {len(soft_violations)} soft constraint violations (total penalty: {total_penalty:.0f})")

    return is_feasible, all_violations


def get_total_soft_penalty(violations: list[ConstraintViolation]) -> float:
    """Calculate total penalty from soft constraint violations."""
    return sum(v.penalty for v in violations if v.severity == "soft")
