"""
solution.py - Solution Data Structures

Defines the solution representation for production scheduling:
- ProductionBlock: A single production run of one SKU on one line
- LineSolution: Complete schedule for one production line
- ScheduleSolution: Complete schedule for all lines
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .params import ProductionParams


# ========================================
# Production Block (Single Production Run)
# ========================================

@dataclass
class ProductionBlock:
    """
    A continuous production run of one SKU on one line.

    Represents a single scheduled production activity, similar to
    how VehicleSolution represents a vehicle's journey in the EV project.

    Attributes:
        block_id: Unique identifier for this block
        line_id: Which production line runs this block
        sku_id: Which SKU is being produced
        start_time: When production starts
        end_time: When production ends
        units_produced: Number of units produced
        changeover_from: Previous SKU (if changeover occurred)
        changeover_time_minutes: Time spent on changeover (0 if first block)

    Example:
        block = ProductionBlock(
            block_id="BLOCK-001",
            line_id="LINE-A",
            sku_id="SKU-001",
            start_time=datetime(2026, 1, 25, 6, 0),
            end_time=datetime(2026, 1, 25, 10, 0),
            units_produced=8000,
            changeover_from=None,
            changeover_time_minutes=0.0,
        )
    """
    block_id: str
    line_id: str
    sku_id: str
    start_time: datetime
    end_time: datetime
    units_produced: int
    changeover_from: str | None = None
    changeover_time_minutes: float = 0.0

    def get_duration_hours(self) -> float:
        """Get total block duration (including changeover) in hours."""
        return (self.end_time - self.start_time).total_seconds() / 3600.0

    def get_production_hours(self) -> float:
        """Get actual production time (excluding changeover) in hours."""
        total_hours = self.get_duration_hours()
        changeover_hours = self.changeover_time_minutes / 60.0
        return max(0.0, total_hours - changeover_hours)

    def get_effective_speed(self) -> float:
        """Calculate effective production speed (units/hour)."""
        hours = self.get_production_hours()
        if hours <= 0:
            return 0.0
        return self.units_produced / hours


# ========================================
# Line Solution (Single Line Schedule)
# ========================================

@dataclass
class LineSolution:
    """
    Complete schedule for a single production line.

    Contains all production blocks assigned to one line, ordered by time.

    Attributes:
        line_id: Which line this schedule is for
        production_blocks: Ordered list of production blocks
    """
    line_id: str
    production_blocks: list[ProductionBlock] = field(default_factory=list)

    def get_total_units(self) -> int:
        """Get total units produced on this line."""
        return sum(block.units_produced for block in self.production_blocks)

    def get_total_production_hours(self) -> float:
        """Get total hours spent actually producing (excluding changeover)."""
        return sum(block.get_production_hours() for block in self.production_blocks)

    def get_total_changeover_time(self) -> float:
        """Get total changeover time in minutes."""
        return sum(block.changeover_time_minutes for block in self.production_blocks)

    def get_num_changeovers(self) -> int:
        """Count number of changeovers (blocks with changeover > 0)."""
        return sum(1 for block in self.production_blocks if block.changeover_time_minutes > 0)

    def get_completion_time(self) -> datetime | None:
        """Get time when last block on this line completes."""
        if not self.production_blocks:
            return None
        return max(block.end_time for block in self.production_blocks)

    def get_start_time(self) -> datetime | None:
        """Get time when first block on this line starts."""
        if not self.production_blocks:
            return None
        return min(block.start_time for block in self.production_blocks)

    def get_utilization(self, available_hours: float) -> float:
        """
        Calculate line utilization as fraction of available time.

        Args:
            available_hours: Total hours the line was available

        Returns:
            Utilization fraction (0.0 to 1.0)
        """
        if available_hours <= 0:
            return 0.0
        production_hours = self.get_total_production_hours()
        return min(1.0, production_hours / available_hours)

    def get_units_by_sku(self) -> dict[str, int]:
        """Get breakdown of units produced by SKU."""
        units = {}
        for block in self.production_blocks:
            units[block.sku_id] = units.get(block.sku_id, 0) + block.units_produced
        return units

    def get_blocks_sorted(self) -> list[ProductionBlock]:
        """Get production blocks sorted by start time."""
        return sorted(self.production_blocks, key=lambda b: b.start_time)

    def has_overlap(self) -> bool:
        """Check if any blocks overlap in time (constraint violation)."""
        sorted_blocks = self.get_blocks_sorted()
        for i in range(len(sorted_blocks) - 1):
            if sorted_blocks[i].end_time > sorted_blocks[i + 1].start_time:
                return True
        return False


# ========================================
# Schedule Solution (All Lines)
# ========================================

@dataclass
class ScheduleSolution:
    """
    Complete production schedule for all lines.

    This is the top-level solution container, similar to FleetSolution
    in the EV routing project.

    Attributes:
        line_solutions: List of LineSolution objects (one per line)
        params: Reference to problem parameters
    """
    line_solutions: list[LineSolution]
    params: ProductionParams

    def get_makespan_hours(self) -> float:
        """
        Get makespan: time from earliest start to latest completion.

        Returns:
            Makespan in hours (0.0 if no production blocks)
        """
        all_starts = []
        all_ends = []

        for ls in self.line_solutions:
            start = ls.get_start_time()
            end = ls.get_completion_time()
            if start:
                all_starts.append(start)
            if end:
                all_ends.append(end)

        if not all_starts or not all_ends:
            return 0.0

        earliest_start = min(all_starts)
        latest_end = max(all_ends)

        return (latest_end - earliest_start).total_seconds() / 3600.0

    def get_completion_time(self) -> datetime | None:
        """Get time when last production block completes."""
        all_ends = []
        for ls in self.line_solutions:
            end = ls.get_completion_time()
            if end:
                all_ends.append(end)
        return max(all_ends) if all_ends else None

    def get_total_units(self) -> int:
        """Get total units produced across all lines."""
        return sum(ls.get_total_units() for ls in self.line_solutions)

    def get_total_changeover_time(self) -> float:
        """Get total changeover time in minutes across all lines."""
        return sum(ls.get_total_changeover_time() for ls in self.line_solutions)

    def get_total_changeovers(self) -> int:
        """Count total number of changeovers across all lines."""
        return sum(ls.get_num_changeovers() for ls in self.line_solutions)

    def get_demand_fulfillment(self) -> dict[str, float]:
        """
        Calculate demand fulfillment percentage for each SKU.

        Returns:
            Dict mapping sku_id -> fulfillment ratio (0.0 to 1.0+)
        """
        # Count produced units by SKU
        produced = {}
        for ls in self.line_solutions:
            for sku_id, units in ls.get_units_by_sku().items():
                produced[sku_id] = produced.get(sku_id, 0) + units

        # Calculate fulfillment ratio for each SKU
        fulfillment = {}
        for sku in self.params.skus:
            demand = sku.demand_units
            made = produced.get(sku.sku_id, 0)
            total_inventory = made + sku.starting_stock
            if demand > 0:
                fulfillment[sku.sku_id] = total_inventory / demand
            else:
                fulfillment[sku.sku_id] = 1.0  # No demand = fully fulfilled

        return fulfillment

    def get_unfulfilled_demand(self) -> dict[str, int]:
        """
        Get unfulfilled demand (shortfall) for each SKU.

        Returns:
            Dict mapping sku_id -> units still needed (0 if fulfilled)
        """
        fulfillment = self.get_demand_fulfillment()
        unfulfilled = {}

        for sku in self.params.skus:
            demand = sku.demand_units
            ratio = fulfillment.get(sku.sku_id, 0.0)
            shortfall = max(0, int(demand * (1.0 - ratio)))
            if shortfall > 0:
                unfulfilled[sku.sku_id] = shortfall

        return unfulfilled

    def get_line_utilizations(self, available_hours_per_line: float) -> dict[str, float]:
        """
        Get utilization for each line.

        Args:
            available_hours_per_line: Hours each line was available

        Returns:
            Dict mapping line_id -> utilization (0.0 to 1.0)
        """
        return {
            ls.line_id: ls.get_utilization(available_hours_per_line)
            for ls in self.line_solutions
        }

    def get_average_utilization(self, available_hours_per_line: float) -> float:
        """Get average utilization across all lines."""
        utils = self.get_line_utilizations(available_hours_per_line)
        if not utils:
            return 0.0
        return sum(utils.values()) / len(utils)

    def get_line_solution(self, line_id: str) -> LineSolution | None:
        """Get the solution for a specific line."""
        for ls in self.line_solutions:
            if ls.line_id == line_id:
                return ls
        return None

    def get_all_blocks(self) -> list[ProductionBlock]:
        """Get all production blocks across all lines."""
        blocks = []
        for ls in self.line_solutions:
            blocks.extend(ls.production_blocks)
        return blocks

    def get_all_blocks_sorted(self) -> list[ProductionBlock]:
        """Get all production blocks sorted by start time."""
        return sorted(self.get_all_blocks(), key=lambda b: b.start_time)

    def get_vehicle_count(self) -> int:
        """Get number of production lines (for API compatibility)."""
        return len(self.line_solutions)

    def summary(self) -> str:
        """Get a text summary of the solution."""
        lines = [
            "=" * 60,
            "SCHEDULE SOLUTION SUMMARY",
            "=" * 60,
            f"Lines: {len(self.line_solutions)}",
            f"Total blocks: {len(self.get_all_blocks())}",
            f"Total units: {self.get_total_units():,}",
            f"Makespan: {self.get_makespan_hours():.1f} hours",
            f"Total changeovers: {self.get_total_changeovers()}",
            f"Total changeover time: {self.get_total_changeover_time():.0f} minutes",
            "",
            "Demand Fulfillment:",
        ]

        for sku_id, ratio in self.get_demand_fulfillment().items():
            status = "✓" if ratio >= 1.0 else "✗"
            lines.append(f"  {status} {sku_id}: {ratio*100:.1f}%")

        lines.append("")
        lines.append("Line Utilization:")
        horizon_hours = self.params.planning_horizon_days * 24
        for line_id, util in self.get_line_utilizations(horizon_hours).items():
            lines.append(f"  {line_id}: {util*100:.1f}%")

        lines.append("=" * 60)
        return "\n".join(lines)
