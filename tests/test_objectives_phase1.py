"""
Test suite for the Phase 1 objective function improvements.

Tests:
- classify_changeover() timing classification
- objective_changeover_with_timing() penalty calculation
- Hard demand constraint in objective_weighted()
- get_demand_fulfillment_pct() calculation
"""

from datetime import datetime, time
from unittest.mock import MagicMock, patch

import pytest

from core.config import (
    PENALTY_FRIDAY_CHANGEOVER,
    PENALTY_INFEASIBLE_SOLUTION,
    PENALTY_MID_SHIFT_CHANGEOVER,
    PENALTY_START_OF_DAY_CHANGEOVER,
    ChangeoverType,
)
from core.objectives import (
    classify_changeover,
    get_demand_fulfillment_pct,
    objective_changeover_with_timing,
    objective_weighted,
)
from core.params import ProductionParams, Shift, make_demo_params
from core.solution import LineSolution, ProductionBlock, ScheduleSolution


class TestClassifyChangeover:
    """Tests for changeover timing classification."""

    @pytest.fixture
    def mock_shifts(self):
        """Create mock shifts for testing."""
        return [
            Shift(
                shift_id="day",
                name="Day Shift",
                start_time=time(6, 0),
                end_time=time(14, 0),
                available_lines=["L1"]
            ),
            Shift(
                shift_id="night",
                name="Night Shift",
                start_time=time(14, 0),
                end_time=time(22, 0),
                available_lines=["L1"]
            )
        ]

    @pytest.fixture
    def mock_params(self, mock_shifts):
        """Create mock params for testing."""
        params = MagicMock(spec=ProductionParams)
        params.shifts = mock_shifts
        return params

    def test_friday_changeover(self, mock_shifts, mock_params):
        """Friday changeovers should be classified as FRIDAY."""
        # Create block starting on Friday at 10:00 (mid-shift)
        friday = datetime(2026, 2, 6, 10, 0)  # This is a Friday
        block = MagicMock(spec=ProductionBlock)
        block.start_time = friday

        result = classify_changeover(block, mock_shifts, mock_params)
        assert result == ChangeoverType.FRIDAY

    def test_start_of_day_changeover(self, mock_shifts, mock_params):
        """Changeovers at day shift start (6 AM) should be START_OF_DAY."""
        # Monday at 6:00 AM (exact shift start)
        monday_morning = datetime(2026, 2, 2, 6, 0)  # Monday
        block = MagicMock(spec=ProductionBlock)
        block.start_time = monday_morning

        result = classify_changeover(block, mock_shifts, mock_params)
        assert result == ChangeoverType.START_OF_DAY

    def test_start_of_shift_changeover(self, mock_shifts, mock_params):
        """Changeovers at non-morning shift start should be START_OF_SHIFT."""
        # Monday at 2:00 PM (night shift start)
        monday_afternoon = datetime(2026, 2, 2, 14, 0)  # Monday
        block = MagicMock(spec=ProductionBlock)
        block.start_time = monday_afternoon

        result = classify_changeover(block, mock_shifts, mock_params)
        assert result == ChangeoverType.START_OF_SHIFT

    def test_mid_shift_changeover(self, mock_shifts, mock_params):
        """Changeovers in middle of shift should be MID_SHIFT."""
        # Monday at 10:00 AM (middle of day shift)
        monday_midday = datetime(2026, 2, 2, 10, 0)  # Monday
        block = MagicMock(spec=ProductionBlock)
        block.start_time = monday_midday

        result = classify_changeover(block, mock_shifts, mock_params)
        assert result == ChangeoverType.MID_SHIFT


class TestObjectiveChangeoverWithTiming:
    """Tests for changeover timing penalty calculation."""

    def test_no_changeovers_zero_penalty(self):
        """Solution with no changeovers should have zero penalty."""
        params = make_demo_params()
        solution = MagicMock(spec=ScheduleSolution)
        solution.params = params

        # Mock line solutions with single-SKU blocks (no changeovers)
        line_solution = MagicMock(spec=LineSolution)
        block1 = MagicMock(spec=ProductionBlock)
        block1.sku_id = "SKU-001"
        block1.start_time = datetime(2026, 2, 2, 6, 0)

        line_solution.get_blocks_sorted.return_value = [block1]
        solution.line_solutions = [line_solution]

        penalty, breakdown = objective_changeover_with_timing(solution)

        assert penalty == 0.0
        assert sum(breakdown.values()) == 0

    def test_friday_changeover_zero_penalty(self):
        """Friday changeovers should have zero penalty."""
        assert PENALTY_FRIDAY_CHANGEOVER == 0.0

    def test_mid_shift_highest_penalty(self):
        """Mid-shift changeovers should have highest penalty."""
        assert PENALTY_MID_SHIFT_CHANGEOVER > PENALTY_START_OF_DAY_CHANGEOVER
        assert PENALTY_START_OF_DAY_CHANGEOVER > PENALTY_FRIDAY_CHANGEOVER


class TestDemandFulfillment:
    """Tests for demand fulfillment calculation."""

    def test_100_percent_demand_met(self):
        """Should return 100% when all demand is met."""
        params = make_demo_params()

        # Create solution that meets all demand
        # Using demo_params which creates balanced demand
        from optimizer.genetic import GeneticOptimizer

        optimizer = GeneticOptimizer(params, population_size=20, generations=5)
        solution = optimizer.solve()

        demand_pct = get_demand_fulfillment_pct(solution)

        # Should be close to 100% for demo params
        assert demand_pct >= 95.0, f"Expected ~100% demand, got {demand_pct}%"


class TestHardDemandConstraint:
    """Tests for the hard demand constraint in objective_weighted."""

    def test_infeasible_with_low_demand(self):
        """Solutions with <100% demand should return INFEASIBLE penalty."""
        params = make_demo_params()

        # Create a deliberately bad solution with no production
        solution = MagicMock(spec=ScheduleSolution)
        solution.params = params
        solution.line_solutions = []

        # Mock methods to return zero production
        solution.get_total_units.return_value = 0
        solution.get_makespan_hours.return_value = 0.0

        # With enforce_demand_hard_constraint=True, should return huge penalty
        # (This will fail in practice since we need real solution, testing pattern)
        with patch('core.objectives.get_demand_fulfillment_pct', return_value=50.0):
            result = objective_weighted(solution, enforce_demand_hard_constraint=True)
            assert result == PENALTY_INFEASIBLE_SOLUTION

    def test_feasible_with_full_demand(self):
        """Solutions with 100% demand should NOT return infeasible penalty."""
        params = make_demo_params()

        from optimizer.genetic import GeneticOptimizer
        optimizer = GeneticOptimizer(params, population_size=20, generations=5)
        solution = optimizer.solve()

        result = objective_weighted(solution, enforce_demand_hard_constraint=True)

        assert result < PENALTY_INFEASIBLE_SOLUTION, \
            f"Expected valid fitness, got infeasible penalty: {result}"


class TestOptimizationHistory:
    """Tests for optimization history and best-keeper logic."""

    def test_add_run_tracks_best(self):
        """Adding runs should track the best one."""
        from datetime import datetime

        from optimizer.ensemble import OptimizationHistory, RunResult

        history = OptimizationHistory()

        # Add first run
        run1 = RunResult(
            run_number=1,
            seed=123,
            timestamp=datetime.now(),
            fitness=500.0,
            demand_pct=100.0,
            is_feasible=True,
            total_changeovers=10,
            changeover_breakdown={},
            solution=MagicMock(),
            elapsed_seconds=1.0
        )

        is_best = history.add_run(run1)
        assert is_best
        assert history.best_ever == run1

        # Add better run
        run2 = RunResult(
            run_number=2,
            seed=456,
            timestamp=datetime.now(),
            fitness=300.0,  # Better (lower)
            demand_pct=100.0,
            is_feasible=True,
            total_changeovers=5,
            changeover_breakdown={},
            solution=MagicMock(),
            elapsed_seconds=1.0
        )

        is_best = history.add_run(run2)
        assert is_best
        assert history.best_ever == run2

        # Add worse run
        run3 = RunResult(
            run_number=3,
            seed=789,
            timestamp=datetime.now(),
            fitness=400.0,  # Worse than run2
            demand_pct=100.0,
            is_feasible=True,
            total_changeovers=8,
            changeover_breakdown={},
            solution=MagicMock(),
            elapsed_seconds=1.0
        )

        is_best = history.add_run(run3)
        assert not is_best
        assert history.best_ever == run2  # Still run2

    def test_feasibility_beats_fitness(self):
        """Feasible solutions should always be preferred over infeasible."""
        from optimizer.ensemble import RunResult

        feasible_run = RunResult(
            run_number=1,
            seed=123,
            timestamp=datetime.now(),
            fitness=1000.0,  # Higher fitness
            demand_pct=100.0,
            is_feasible=True,
            total_changeovers=10,
            changeover_breakdown={},
            solution=MagicMock(),
            elapsed_seconds=1.0
        )

        infeasible_run = RunResult(
            run_number=2,
            seed=456,
            timestamp=datetime.now(),
            fitness=100.0,  # Lower fitness but infeasible
            demand_pct=80.0,
            is_feasible=False,
            total_changeovers=2,
            changeover_breakdown={},
            solution=MagicMock(),
            elapsed_seconds=1.0
        )

        assert feasible_run.is_better_than(infeasible_run)
        assert not infeasible_run.is_better_than(feasible_run)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
