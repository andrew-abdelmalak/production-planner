"""
ensemble.py - Ensemble Optimizer with Progress Reporting and History

Implements a high-quality optimization strategy that:
1. Runs Genetic Algorithm 5 times with different random seeds
2. Selects the best solution based on feasibility > fitness > demand
3. Reports progress to enable visual feedback in the dashboard
4. Tracks optimization history for comparing runs and keeping best solution
5. Optionally runs GA instances in parallel for faster results
"""

import time
import random
import os
from datetime import datetime
from typing import Optional, Callable, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed

from core.params import ProductionParams
from core.solution import ScheduleSolution
from core.constraints import validate_solution
from core.objectives import evaluate_solution, get_demand_fulfillment_pct, objective_changeover_with_timing


@dataclass
class OptimizationProgress:
    """Current optimization progress state."""
    phase: str  # e.g., "Initializing", "Running GA 1/5", "Evaluating"
    current_run: int
    total_runs: int
    percent_complete: float
    best_fitness: Optional[float] = None
    best_demand_pct: Optional[float] = None
    elapsed_seconds: float = 0.0
    message: str = ""


@dataclass 
class RunResult:
    """Result from a single optimization run."""
    run_number: int
    seed: int
    timestamp: datetime
    fitness: float
    demand_pct: float
    is_feasible: bool
    total_changeovers: int
    changeover_breakdown: Dict[str, int]
    solution: ScheduleSolution
    elapsed_seconds: float
    
    def is_better_than(self, other: 'RunResult') -> bool:
        """Check if this run is better than another."""
        # Feasibility first
        if self.is_feasible and not other.is_feasible:
            return True
        if not self.is_feasible and other.is_feasible:
            return False
        # Then fitness (lower is better)
        return self.fitness < other.fitness


@dataclass
class OptimizationHistory:
    """
    Tracks all optimization runs and maintains the best solution.
    
    Use this to compare runs and implement "best-keeper" logic
    that prevents regression to worse solutions.
    """
    runs: List[RunResult] = field(default_factory=list)
    best_ever: Optional[RunResult] = None
    previous_session_best: Optional[RunResult] = None
    
    def add_run(self, run: RunResult) -> bool:
        """
        Add a run to history and update best_ever if improved.
        
        Returns:
            True if this run is the new best, False otherwise
        """
        self.runs.append(run)
        
        if self.best_ever is None or run.is_better_than(self.best_ever):
            self.best_ever = run
            return True
        return False
    
    def get_best_solution(self) -> Optional[ScheduleSolution]:
        """Get the best solution found."""
        if self.best_ever:
            return self.best_ever.solution
        return None
    
    def compare_with_previous(self, new_best: RunResult) -> Dict[str, Any]:
        """
        Compare new best with previous session's best.
        
        Returns dict with comparison info for dashboard display.
        """
        result = {
            'new_run': new_best,
            'is_improvement': True,
            'message': 'First optimization run'
        }
        
        if self.previous_session_best:
            if new_best.is_better_than(self.previous_session_best):
                improvement = self.previous_session_best.fitness - new_best.fitness
                result['is_improvement'] = True
                result['message'] = f"🎉 New best! Fitness improved by {improvement:.1f}"
                result['previous'] = self.previous_session_best
            else:
                result['is_improvement'] = False
                result['message'] = "Previous solution still best. Keeping previous."
                result['previous'] = self.previous_session_best
        
        return result
    
    def get_runs_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all runs for dashboard display."""
        return [
            {
                'run': r.run_number,
                'fitness': r.fitness,
                'demand_pct': r.demand_pct,
                'feasible': r.is_feasible,
                'changeovers': r.total_changeovers,
                'is_best': r == self.best_ever,
                'timestamp': r.timestamp.isoformat()
            }
            for r in sorted(self.runs, key=lambda x: x.fitness)
        ]


# Type alias for progress callback
ProgressCallback = Callable[[OptimizationProgress], None]


class EnsembleOptimizer:
    """
    High-quality ensemble optimizer using multiple GA runs.
    
    Strategy:
    - Runs 5 independent Genetic Algorithm optimizations with different seeds
    - Each run uses pop=100, gen=50 for thorough exploration
    - Selects best solution by: Feasibility > Fitness Score > Demand %
    - Reports progress via callback for visual feedback
    """
    
    def __init__(
        self,
        params: ProductionParams,
        num_runs: int = 5,
        population_size: int = 100,
        generations: int = 50,
        progress_callback: Optional[ProgressCallback] = None,
        verbose: bool = True
    ):
        self.params = params
        self.num_runs = num_runs
        self.population_size = population_size
        self.generations = generations
        self.progress_callback = progress_callback
        self.verbose = verbose
    
    def _report_progress(self, progress: OptimizationProgress) -> None:
        """Report progress via callback and optionally print."""
        if self.progress_callback:
            self.progress_callback(progress)
        if self.verbose:
            print(f"[{progress.percent_complete:5.1f}%] {progress.phase}: {progress.message}")
    
    def solve(self, history: Optional[OptimizationHistory] = None) -> Tuple[ScheduleSolution, OptimizationHistory]:
        """
        Run the ensemble optimization and return the best solution with history.
        
        Args:
            history: Optional existing history to continue from (for best-keeper)
        
        Returns:
            Tuple of (best_solution, optimization_history)
        """
        from optimizer.genetic import GeneticOptimizer
        from core.objectives import objective_demand_detailed
        
        start_time = time.time()
        
        # Initialize or continue history
        if history is None:
            history = OptimizationHistory()
        else:
            # Save previous best for comparison
            history.previous_session_best = history.best_ever
        
        # Phase 1: Initialize
        self._report_progress(OptimizationProgress(
            phase="Initializing",
            current_run=0,
            total_runs=self.num_runs,
            percent_complete=0.0,
            elapsed_seconds=0.0,
            message="Preparing optimization..."
        ))
        
        # Phase 2: Run GA multiple times
        for run_idx in range(self.num_runs):
            run_start = time.time()
            seed = random.randint(1, 100000)
            random.seed(seed)
            
            self._report_progress(OptimizationProgress(
                phase=f"Running GA {run_idx + 1}/{self.num_runs}",
                current_run=run_idx + 1,
                total_runs=self.num_runs,
                percent_complete=(run_idx / self.num_runs) * 80,  # 80% for GA runs
                elapsed_seconds=time.time() - start_time,
                message=f"Optimizing with seed {seed}..."
            ))
            
            # Run genetic algorithm
            optimizer = GeneticOptimizer(
                self.params,
                population_size=self.population_size,
                generations=self.generations,
                verbose=False
            )
            solution = optimizer.solve()
            
            # Evaluate solution
            is_feasible, violations = validate_solution(solution, verbose=False)
            eval_results = evaluate_solution(solution, verbose=False)
            
            # Calculate demand fulfillment
            demand_pct = get_demand_fulfillment_pct(solution)
            
            # Calculate changeover breakdown
            changeover_penalty, changeover_breakdown = objective_changeover_with_timing(solution)
            total_changeovers = sum(changeover_breakdown.values())
            
            # Create run result
            run_result = RunResult(
                run_number=len(history.runs) + 1,
                seed=seed,
                timestamp=datetime.now(),
                fitness=eval_results["weighted_objective"],
                demand_pct=demand_pct,
                is_feasible=is_feasible,
                total_changeovers=total_changeovers,
                changeover_breakdown=changeover_breakdown,
                solution=solution,
                elapsed_seconds=time.time() - run_start
            )
            
            # Add to history (tracks if it's the new best)
            is_new_best = history.add_run(run_result)
            
            # Report intermediate best
            best_marker = " 🎯 NEW BEST!" if is_new_best else ""
            self._report_progress(OptimizationProgress(
                phase=f"Completed GA {run_idx + 1}/{self.num_runs}",
                current_run=run_idx + 1,
                total_runs=self.num_runs,
                percent_complete=((run_idx + 1) / self.num_runs) * 80,
                best_fitness=history.best_ever.fitness if history.best_ever else None,
                best_demand_pct=history.best_ever.demand_pct if history.best_ever else None,
                elapsed_seconds=time.time() - start_time,
                message=f"Run {run_idx + 1}: Fitness={run_result.fitness:.0f}, Demand={demand_pct:.1f}%{best_marker}"
            ))
        
        # Phase 3: Select best solution
        self._report_progress(OptimizationProgress(
            phase="Selecting Best",
            current_run=self.num_runs,
            total_runs=self.num_runs,
            percent_complete=90.0,
            elapsed_seconds=time.time() - start_time,
            message="Analyzing results..."
        ))
        
        # Compare with previous session
        best_info = history.best_ever
        comparison = history.compare_with_previous(best_info)
        
        # Best-keeper logic: use previous if better
        if not comparison['is_improvement'] and history.previous_session_best:
            best_solution = history.previous_session_best.solution
            best_info = history.previous_session_best
            if self.verbose:
                print(f"\n⚠️ {comparison['message']}")
        else:
            best_solution = best_info.solution
            if self.verbose and comparison['is_improvement']:
                print(f"\n{comparison['message']}")
        
        # Phase 4: Complete
        total_time = time.time() - start_time
        self._report_progress(OptimizationProgress(
            phase="Complete",
            current_run=self.num_runs,
            total_runs=self.num_runs,
            percent_complete=100.0,
            best_fitness=best_info.fitness,
            best_demand_pct=best_info.demand_pct,
            elapsed_seconds=total_time,
            message=f"Best: Run {best_info.run_number} (Fitness: {best_info.fitness:.0f}, Demand: {best_info.demand_pct:.1f}%)"
        ))
        
        if self.verbose:
            print(f"\n{'='*50}")
            print(f"ENSEMBLE OPTIMIZATION COMPLETE")
            print(f"{'='*50}")
            print(f"Total Time: {total_time:.2f}s")
            print(f"Total Runs (all sessions): {len(history.runs)}")
            print(f"Best Run: #{best_info.run_number} (seed={best_info.seed})")
            print(f"Feasible: {'Yes' if best_info.is_feasible else 'No'}")
            print(f"Fitness: {best_info.fitness:.2f}")
            print(f"Demand Fulfillment: {best_info.demand_pct:.1f}%")
            print(f"Total Changeovers: {best_info.total_changeovers}")
            print(f"{'='*50}\n")
        
        return best_solution, history


def run_ensemble_optimization(
    params: ProductionParams,
    history: Optional[OptimizationHistory] = None,
    progress_callback: Optional[ProgressCallback] = None,
    verbose: bool = True
) -> Tuple[ScheduleSolution, OptimizationHistory]:
    """
    Convenience function to run ensemble optimization with history tracking.
    
    Args:
        params: Production parameters
        history: Optional existing history (for best-keeper across sessions)
        progress_callback: Optional callback for progress updates
        verbose: Print progress to console
    
    Returns:
        Tuple of (best_solution, optimization_history)
    """
    from core.config import DEFAULT_ENSEMBLE_RUNS, DEFAULT_POPULATION_SIZE, DEFAULT_GENERATIONS
    
    optimizer = EnsembleOptimizer(
        params,
        num_runs=DEFAULT_ENSEMBLE_RUNS,
        population_size=DEFAULT_POPULATION_SIZE,
        generations=DEFAULT_GENERATIONS,
        progress_callback=progress_callback,
        verbose=verbose
    )
    return optimizer.solve(history)


# ============================================================
# Parallel Execution Support
# ============================================================

def _run_single_ga(args: Tuple) -> Dict[str, Any]:
    """
    Run a single GA optimization (for use in multiprocessing).
    
    This function runs in a separate process, so it must be picklable.
    
    Args:
        args: Tuple of (params, population_size, generations, seed, run_number)
    
    Returns:
        Dict with solution data (not ScheduleSolution object due to pickling)
    """
    from optimizer.genetic import GeneticOptimizer
    
    params, population_size, generations, seed, run_number = args
    
    random.seed(seed)
    
    start_time = time.time()
    
    optimizer = GeneticOptimizer(
        params,
        population_size=population_size,
        generations=generations,
        verbose=False
    )
    solution = optimizer.solve()
    
    # Evaluate solution
    is_feasible, _ = validate_solution(solution, verbose=False)
    eval_results = evaluate_solution(solution, verbose=False)
    demand_pct = get_demand_fulfillment_pct(solution)
    changeover_penalty, changeover_breakdown = objective_changeover_with_timing(solution)
    total_changeovers = sum(changeover_breakdown.values())
    
    elapsed = time.time() - start_time
    
    return {
        'run_number': run_number,
        'seed': seed,
        'fitness': eval_results["weighted_objective"],
        'demand_pct': demand_pct,
        'is_feasible': is_feasible,
        'total_changeovers': total_changeovers,
        'changeover_breakdown': changeover_breakdown,
        'solution': solution,  # Note: may need serialization for cross-process
        'elapsed_seconds': elapsed
    }


def run_parallel_ensemble(
    params: ProductionParams,
    num_runs: int = 5,
    population_size: int = 100,
    generations: int = 75,
    max_workers: int = None,
    verbose: bool = True
) -> Tuple[ScheduleSolution, OptimizationHistory]:
    """
    Run ensemble optimization with parallel GA runs.
    
    Uses ProcessPoolExecutor to run multiple GA instances simultaneously.
    This can significantly speed up optimization on multi-core systems.
    
    Args:
        params: Production parameters
        num_runs: Number of independent GA runs
        population_size: GA population size
        generations: Number of GA generations
        max_workers: Maximum parallel workers (default: CPU count)
        verbose: Print progress to console
    
    Returns:
        Tuple of (best_solution, optimization_history)
    """
    from core.config import DEFAULT_POPULATION_SIZE, DEFAULT_GENERATIONS
    
    start_time = time.time()
    
    # Use config defaults if not specified
    population_size = population_size or DEFAULT_POPULATION_SIZE
    generations = generations or DEFAULT_GENERATIONS
    max_workers = max_workers or min(num_runs, os.cpu_count() or 4)
    
    if verbose:
        print(f"{'='*50}")
        print(f"PARALLEL ENSEMBLE OPTIMIZATION")
        print(f"{'='*50}")
        print(f"Runs: {num_runs}, Workers: {max_workers}")
        print(f"Population: {population_size}, Generations: {generations}")
        print()
    
    # Prepare run arguments
    seeds = [random.randint(1, 100000) for _ in range(num_runs)]
    run_args = [
        (params, population_size, generations, seed, i + 1)
        for i, seed in enumerate(seeds)
    ]
    
    history = OptimizationHistory()
    
    # Run in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        futures = {
            executor.submit(_run_single_ga, args): args[4]  # args[4] = run_number
            for args in run_args
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            run_number = futures[future]
            try:
                result = future.result()
                
                # Create RunResult from dict
                run_result = RunResult(
                    run_number=result['run_number'],
                    seed=result['seed'],
                    timestamp=datetime.now(),
                    fitness=result['fitness'],
                    demand_pct=result['demand_pct'],
                    is_feasible=result['is_feasible'],
                    total_changeovers=result['total_changeovers'],
                    changeover_breakdown=result['changeover_breakdown'],
                    solution=result['solution'],
                    elapsed_seconds=result['elapsed_seconds']
                )
                
                is_new_best = history.add_run(run_result)
                
                if verbose:
                    best_marker = " 🎯 NEW BEST!" if is_new_best else ""
                    print(f"[Parallel] Run {run_number}/{num_runs}: "
                          f"Fitness={result['fitness']:.0f}, "
                          f"Demand={result['demand_pct']:.1f}%{best_marker}")
                    
            except Exception as e:
                if verbose:
                    print(f"[Parallel] Run {run_number} failed: {e}")
    
    total_time = time.time() - start_time
    
    best_solution = history.get_best_solution()
    best_info = history.best_ever
    
    if verbose:
        print()
        print(f"{'='*50}")
        print(f"PARALLEL OPTIMIZATION COMPLETE")
        print(f"{'='*50}")
        print(f"Total Time: {total_time:.2f}s "
              f"(vs ~{total_time * max_workers:.0f}s sequential)")
        print(f"Best Run: #{best_info.run_number} (seed={best_info.seed})")
        print(f"Feasible: {'Yes' if best_info.is_feasible else 'No'}")
        print(f"Fitness: {best_info.fitness:.2f}")
        print(f"Demand: {best_info.demand_pct:.1f}%")
        print(f"Changeovers: {best_info.total_changeovers}")
        print(f"{'='*50}")
    
    return best_solution, history

