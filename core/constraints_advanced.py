"""
constraints_advanced.py - Advanced Production Constraints

Defines constraint classes for complex scheduling requirements:
- Exclusive SKU (no parallel production)
- Shift-based restrictions
- Sequence restrictions
- Minimum run length
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .solution import ScheduleSolution, ProductionBlock


# ========================================
# Constraint Base Class
# ========================================

@dataclass
class Constraint:
    """Base class for all constraints."""
    name: str
    description: str = ""
    is_hard: bool = True  # Hard constraints must be satisfied; soft can be violated with penalty
    
    def validate(self, solution: "ScheduleSolution") -> Tuple[bool, List[str]]:
        """
        Validate the constraint against a solution.
        
        Returns:
            Tuple of (is_satisfied, list of violation messages)
        """
        raise NotImplementedError("Subclasses must implement validate()")


# ========================================
# Exclusive SKU Constraint
# ========================================

@dataclass
class ExclusiveSKUConstraint(Constraint):
    """
    Constraint that prevents an SKU from being produced on multiple lines simultaneously.
    
    Use case: Some products cannot be run in parallel due to shared resources
    (e.g., same ingredients, same quality control team needed).
    
    Attributes:
        sku_id: The SKU that must not run in parallel
    
    Example:
        constraint = ExclusiveSKUConstraint(
            name="SKU-002 Exclusive",
            sku_id="SKU-002",
            description="SKU-002 requires dedicated QC team"
        )
    """
    sku_id: str = ""
    
    def validate(self, solution: "ScheduleSolution") -> Tuple[bool, List[str]]:
        violations = []
        
        # Get all blocks for this SKU
        sku_blocks = [
            block for block in solution.get_all_blocks()
            if block.sku_id == self.sku_id
        ]
        
        # Check for overlapping time periods
        for i, block1 in enumerate(sku_blocks):
            for block2 in sku_blocks[i+1:]:
                # Different lines, same SKU - check for overlap
                if block1.line_id != block2.line_id:
                    if self._blocks_overlap(block1, block2):
                        violations.append(
                            f"SKU {self.sku_id} runs simultaneously on "
                            f"{block1.line_id} and {block2.line_id} "
                            f"({block1.start_time} - {block1.end_time})"
                        )
        
        return len(violations) == 0, violations
    
    def _blocks_overlap(self, b1: "ProductionBlock", b2: "ProductionBlock") -> bool:
        """Check if two blocks overlap in time."""
        return not (b1.end_time <= b2.start_time or b2.end_time <= b1.start_time)


# ========================================
# Shift-Based SKU Restriction
# ========================================

@dataclass  
class ShiftRestrictionConstraint(Constraint):
    """
    Constraint that limits an SKU to specific shifts.
    
    Use case: Some products can only be made during certain shifts
    (e.g., night shift only, or never on night shift due to noise).
    
    Attributes:
        sku_id: The SKU with the restriction
        allowed_shifts: List of shift IDs where this SKU can be produced
        
    Example:
        constraint = ShiftRestrictionConstraint(
            name="SKU-003 Day Only",
            sku_id="SKU-003",
            allowed_shifts=["SHIFT-1", "SHIFT-2"],
            description="SKU-003 cannot run at night due to noise"
        )
    """
    sku_id: str = ""
    allowed_shifts: List[str] = field(default_factory=list)
    
    def validate(self, solution: "ScheduleSolution") -> Tuple[bool, List[str]]:
        violations = []
        
        # Get blocks for this SKU
        sku_blocks = [
            b for b in solution.get_all_blocks()
            if b.sku_id == self.sku_id
        ]
        
        if not sku_blocks:
            return True, []
            
        # We need to map blocks to shifts. 
        # For simplicity in this constraint, we check if the block's line
        # and time roughly correspond to the allowed shifts.
        # A more rigorous check would require mapping exact start/end times to shift windows.
        
        # Get all defined shifts from params
        all_shifts = solution.params.shifts
        allowed_shift_objs = [s for s in all_shifts if s.shift_id in self.allowed_shifts]
        
        if not allowed_shift_objs and self.allowed_shifts:
            # Constraint exists but no matching shift definitions found
            return False, [f"Allowed shifts {self.allowed_shifts} not found in definitions"]

        for block in sku_blocks:
            # Check if this block fits into ANY of the allowed shifts
            # This is complex because shifts repeat daily.
            # Simplified check: Check if block START time falls within allowed shift hours
            # regardless of day.
            
            block_start_time = block.start_time.time()
            is_valid_shift = False
            
            for shift in allowed_shift_objs:
                # Check line availability first
                if block.line_id not in shift.available_lines:
                    continue
                    
                # Check time window
                # Handle overnight shifts (e.g. 22:00 to 06:00)
                if shift.start_time <= shift.end_time:
                    # Standard day shift
                    if shift.start_time <= block_start_time < shift.end_time:
                        is_valid_shift = True
                        break
                else:
                    # Overnight shift
                    if block_start_time >= shift.start_time or block_start_time < shift.end_time:
                        is_valid_shift = True
                        break
            
            if not is_valid_shift:
                violations.append(
                    f"SKU {self.sku_id} scheduled on {block.line_id} at {block.start_time} "
                    f"which does not match allowed shifts {self.allowed_shifts}"
                )
        
        return len(violations) == 0, violations


# ========================================
# Sequence Restriction Constraint
# ========================================

@dataclass
class SequenceRestrictionConstraint(Constraint):
    """
    Constraint that prevents one SKU from immediately following another.
    
    Use case: Some product transitions are problematic
    (e.g., flavored to unflavored requires extra cleaning).
    
    Attributes:
        from_sku: SKU that was just produced
        to_sku: SKU that cannot immediately follow
        applies_to_lines: Specific lines (empty = all lines)
    
    Example:
        constraint = SequenceRestrictionConstraint(
            name="No Juice to Water",
            from_sku="SKU-003",  # Juice
            to_sku="SKU-001",    # Water
            description="Extra cleaning needed between juice and water"
        )
    """
    from_sku: str = ""
    to_sku: str = ""
    applies_to_lines: List[str] = field(default_factory=list)
    
    def validate(self, solution: "ScheduleSolution") -> Tuple[bool, List[str]]:
        violations = []
        
        for line_sol in solution.line_solutions:
            # Skip if constraint doesn't apply to this line
            if self.applies_to_lines and line_sol.line_id not in self.applies_to_lines:
                continue
            
            # Check consecutive blocks
            sorted_blocks = line_sol.get_blocks_sorted()
            for i in range(len(sorted_blocks) - 1):
                current = sorted_blocks[i]
                next_block = sorted_blocks[i + 1]
                
                if current.sku_id == self.from_sku and next_block.sku_id == self.to_sku:
                    violations.append(
                        f"Invalid sequence on {line_sol.line_id}: "
                        f"{self.from_sku} → {self.to_sku} at {current.end_time}"
                    )
        
        return len(violations) == 0, violations


# ========================================
# Minimum Run Length Constraint
# ========================================

@dataclass
class MinRunLengthConstraint(Constraint):
    """
    Constraint that ensures an SKU runs for a minimum duration once started.
    
    Use case: Some products need minimum batch size for quality/efficiency.
    
    Attributes:
        sku_id: The SKU with the minimum run requirement
        min_hours: Minimum production run length in hours
    
    Example:
        constraint = MinRunLengthConstraint(
            name="SKU-004 Min 4 Hours",
            sku_id="SKU-004",
            min_hours=4.0,
            description="SKU-004 needs 4h run for quality"
        )
    """
    sku_id: str = ""
    min_hours: float = 1.0
    
    def validate(self, solution: "ScheduleSolution") -> Tuple[bool, List[str]]:
        violations = []
        
        for block in solution.get_all_blocks():
            if block.sku_id == self.sku_id:
                run_hours = block.get_production_hours()
                if run_hours < self.min_hours:
                    violations.append(
                        f"{self.sku_id} on {block.line_id}: "
                        f"run length {run_hours:.1f}h < minimum {self.min_hours}h"
                    )
        
        return len(violations) == 0, violations


# ========================================
# Constraint Collection
# ========================================

@dataclass
class ConstraintSet:
    """
    Collection of constraints to validate against a solution.
    """
    constraints: List[Constraint] = field(default_factory=list)
    
    def add(self, constraint: Constraint) -> None:
        """Add a constraint to the set."""
        self.constraints.append(constraint)
    
    def validate_all(self, solution: "ScheduleSolution") -> Tuple[bool, List[str]]:
        """
        Validate all constraints against a solution.
        
        Returns:
            Tuple of (all_satisfied, list of all violation messages)
        """
        all_violations = []
        all_satisfied = True
        
        for constraint in self.constraints:
            satisfied, violations = constraint.validate(solution)
            if not satisfied and constraint.is_hard:
                all_satisfied = False
            all_violations.extend(violations)
        
        return all_satisfied, all_violations
    
    def get_exclusive_sku_constraints(self) -> List[ExclusiveSKUConstraint]:
        """Get all exclusive SKU constraints."""
        return [c for c in self.constraints if isinstance(c, ExclusiveSKUConstraint)]
    
    def get_sequence_restrictions(self) -> List[SequenceRestrictionConstraint]:
        """Get all sequence restriction constraints."""
        return [c for c in self.constraints if isinstance(c, SequenceRestrictionConstraint)]


# ========================================
# Factory Functions
# ========================================

def make_exclusive_sku(sku_id: str, description: str = "") -> ExclusiveSKUConstraint:
    """Create an exclusive SKU constraint."""
    return ExclusiveSKUConstraint(
        name=f"{sku_id} Exclusive",
        sku_id=sku_id,
        description=description or f"{sku_id} cannot run on multiple lines simultaneously"
    )


def make_sequence_restriction(from_sku: str, to_sku: str, description: str = "") -> SequenceRestrictionConstraint:
    """Create a sequence restriction constraint."""
    return SequenceRestrictionConstraint(
        name=f"No {from_sku} → {to_sku}",
        from_sku=from_sku,
        to_sku=to_sku,
        description=description or f"{to_sku} cannot immediately follow {from_sku}"
    )


def make_min_run_length(sku_id: str, min_hours: float) -> MinRunLengthConstraint:
    """Create a minimum run length constraint."""
    return MinRunLengthConstraint(
        name=f"{sku_id} Min {min_hours}h",
        sku_id=sku_id,
        min_hours=min_hours,
        description=f"{sku_id} must run for at least {min_hours} hours"
    )
