"""
genetic.py - Genetic Algorithm Optimizer for Production Scheduling

Implements an evolution-based optimization algorithm that:
1. Encodes schedules as chromosomes (gene = SKU assignment to line + time slot)
2. Evolves population through selection, crossover, and mutation
3. Uses fitness function based on weighted objectives

Enhancements:
- Changeover-aware greedy initialization (groups SKU families)
- Feasibility pre-check to skip obviously bad solutions
- Uses centralized config for all parameters
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

# Import centralized configuration
from core.config import (
    DEFAULT_CROSSOVER_RATE,
    DEFAULT_ELITISM,
    DEFAULT_GENERATIONS,
    DEFAULT_MUTATION_RATE,
    DEFAULT_POPULATION_SIZE,
    DEFAULT_TOURNAMENT_SIZE,
    PENALTY_INFEASIBLE_SOLUTION,
)
from core.constraints import validate_solution
from core.objectives import (
    get_demand_fulfillment_pct,
    objective_changeover_with_timing,
    objective_weighted,
)
from core.params import ProductionParams
from core.solution import LineSolution, ProductionBlock, ScheduleSolution


@dataclass
class Gene:
    """A single gene representing one production assignment."""
    sku_id: str
    line_id: str
    units: int
    order: int  # Sequence order within the chromosome


@dataclass
class Chromosome:
    """A chromosome representing a complete production schedule."""
    genes: list[Gene]
    fitness: float = float('inf')

    def copy(self) -> Chromosome:
        """Create a deep copy of this chromosome."""
        return Chromosome(
            genes=[Gene(g.sku_id, g.line_id, g.units, g.order) for g in self.genes],
            fitness=self.fitness
        )


class GeneticOptimizer:
    """
    Genetic Algorithm optimizer for production scheduling.

    Strategy:
    1. Initialize population with random + greedy solutions
    2. Evaluate fitness using weighted objectives
    3. Select parents via tournament selection
    4. Create offspring via crossover and mutation
    5. Replace worst individuals with offspring
    6. Repeat until convergence or max generations

    Attributes:
        params: Production parameters
        population_size: Number of individuals in population
        generations: Maximum number of generations
        mutation_rate: Probability of mutation per gene
        crossover_rate: Probability of crossover
        tournament_size: Number of individuals in tournament selection
        elitism: Number of best individuals to preserve
        verbose: Print progress messages
        progress_callback: Optional callback for progress reporting
    """

    def __init__(
        self,
        params: ProductionParams,
        population_size: int = None,
        generations: int = None,
        mutation_rate: float = None,
        crossover_rate: float = None,
        tournament_size: int = None,
        elitism: int = None,
        verbose: bool = False,
        progress_callback: Callable[[int, int, float, float], None] | None = None
    ):
        self.params = params
        # Use defaults from config if not specified
        self.population_size = population_size or DEFAULT_POPULATION_SIZE
        self.generations = generations or DEFAULT_GENERATIONS
        self.mutation_rate = mutation_rate or DEFAULT_MUTATION_RATE
        self.crossover_rate = crossover_rate or DEFAULT_CROSSOVER_RATE
        self.tournament_size = tournament_size or DEFAULT_TOURNAMENT_SIZE
        self.elitism = elitism or DEFAULT_ELITISM
        self.verbose = verbose
        self.progress_callback = progress_callback

        # Cache line-SKU compatibility
        self._compatible_lines = self._build_compatibility_map()
        self._uptime_windows: dict[str, list[tuple[float, float]]] = {}
        self._calculate_shift_downtimes()

        # Pre-compute SKU families for changeover-aware greedy
        self._sku_families = self._group_skus_by_family()

    @staticmethod
    def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Merge overlapping or adjacent [start, end] intervals."""
        if not intervals:
            return []
        sorted_intervals = sorted(intervals)
        merged = [sorted_intervals[0]]
        for start, end in sorted_intervals[1:]:
            prev_start, prev_end = merged[-1]
            if start <= prev_end + 1e-9:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))
        return merged

    def _calculate_shift_downtimes(self):
        """Convert shifts into uptime and downtime windows for each line."""
        horizon_hours = float(self.params.planning_horizon_days) * 24.0
        current_date = self.params.start_date.date()
        days_to_check = int(self.params.planning_horizon_days) + 2

        for line in self.params.lines:
            # Preserve caller-supplied static downtime windows across repeated optimizer runs
            if not hasattr(line, "_static_downtime_windows"):
                line._static_downtime_windows = list(getattr(line, "downtime_windows", []) or [])
            static_downtimes = list(line._static_downtime_windows)

            uptimes: list[tuple[float, float]] = []
            for day_offset in range(-1, days_to_check):
                check_date = current_date + timedelta(days=day_offset)
                for shift in self.params.shifts:
                    if line.line_id not in shift.available_lines:
                        continue
                    if not shift.matches_date(check_date):
                        continue

                    start_dt = datetime.combine(check_date, shift.start_time)
                    if shift.end_time <= shift.start_time:
                        end_dt = datetime.combine(check_date + timedelta(days=1), shift.end_time)
                    else:
                        end_dt = datetime.combine(check_date, shift.end_time)

                    start_offset = (start_dt - self.params.start_date).total_seconds() / 3600.0
                    end_offset = (end_dt - self.params.start_date).total_seconds() / 3600.0

                    if end_offset > 0:
                        uptimes.append((max(0.0, start_offset), end_offset))

            merged_uptimes = self._merge_intervals(uptimes)

            if not merged_uptimes:
                downtimes = self._merge_intervals(static_downtimes + [(0.0, horizon_hours + 1000.0)])
                line.downtime_windows = downtimes
                self._uptime_windows[line.line_id] = []
                continue

            shift_downtimes: list[tuple[float, float]] = []
            last_end = 0.0
            for start, end in merged_uptimes:
                if start > last_end:
                    shift_downtimes.append((last_end, start))
                last_end = max(last_end, end)
            shift_downtimes.append((last_end, horizon_hours + 1000.0))

            all_downtimes = self._merge_intervals(static_downtimes + shift_downtimes)
            line.downtime_windows = all_downtimes

            # Clamp uptimes to planning horizon and subtract static downtimes for scheduling
            effective_uptimes: list[tuple[float, float]] = []
            for u_start, u_end in merged_uptimes:
                clamped_u_start = max(0.0, u_start)
                clamped_u_end = min(horizon_hours, u_end)
                if clamped_u_end <= clamped_u_start:
                    continue
                cursor = clamped_u_start
                for d_start, d_end in all_downtimes:
                    if d_end <= cursor:
                        continue
                    if d_start >= clamped_u_end:
                        break
                    if d_start > cursor:
                        effective_uptimes.append((cursor, min(clamped_u_end, d_start)))
                    cursor = max(cursor, d_end)
                    if cursor >= clamped_u_end:
                        break
                if cursor < clamped_u_end:
                    effective_uptimes.append((cursor, clamped_u_end))
            self._uptime_windows[line.line_id] = effective_uptimes

    def _build_compatibility_map(self) -> dict[str, list[str]]:
        """Build map of SKU -> compatible line IDs."""
        compat = {}
        for sku in self.params.skus:
            compat[sku.sku_id] = [
                line.line_id for line in self.params.lines
                if line.can_produce(sku.sku_id)
            ]
        return compat

    def _group_skus_by_family(self) -> dict[str, list]:
        """
        Group SKUs by "family" to minimize changeovers.

        SKUs are grouped if they have:
        1. Same compatible lines (can run on same equipment)
        2. Low or zero changeover cost between them

        Returns:
            Dict mapping family_key -> list of SKU objects
        """
        families = {}

        for sku in self.params.skus:
            # Create family key based on compatible lines
            compatible_lines = tuple(sorted(self._compatible_lines.get(sku.sku_id, [])))

            if compatible_lines not in families:
                families[compatible_lines] = []
            families[compatible_lines].append(sku)

        # Sort each family by priority (highest priority first = lower number)
        for family_key in families:
            families[family_key].sort(key=lambda s: s.priority)

        return families

    def _quick_feasibility_check(self, chromosome: Chromosome) -> bool:
        """
        Quick check to reject obviously infeasible solutions.

        Checks (without full evaluation):
        1. All SKUs are assigned
        2. Total units >= demand for each SKU
        3. Lines are compatible with assigned SKUs

        Returns:
            True if solution MIGHT be feasible (worth full evaluation)
            False if definitely infeasible (skip full evaluation)
        """
        # Count units per SKU
        sku_units = {}
        for gene in chromosome.genes:
            sku_units[gene.sku_id] = sku_units.get(gene.sku_id, 0) + gene.units

            # Check line compatibility
            compatible = self._compatible_lines.get(gene.sku_id, [])
            if gene.line_id not in compatible:
                return False  # Invalid line assignment

        # Check all SKUs have enough units to meet demand
        for sku in self.params.skus:
            required = max(0, sku.demand_units - sku.starting_stock)
            assigned = sku_units.get(sku.sku_id, 0)
            if assigned < required * 0.95:  # Allow 5% tolerance
                return False

        return True

    def solve(self) -> ScheduleSolution:
        """
        Run the genetic algorithm optimization.

        Returns:
            ScheduleSolution: Best schedule found
        """
        start_time = time.time()

        if self.verbose:
            print("=" * 60)
            print("GENETIC ALGORITHM OPTIMIZER")
            print("=" * 60)
            print(f"Population: {self.population_size}")
            print(f"Generations: {self.generations}")
            print(f"Mutation rate: {self.mutation_rate}")
            print()

        # Initialize population
        population = self._initialize_population()

        # Evaluate initial population
        for chrom in population:
            chrom.fitness = self._evaluate_fitness(chrom)

        # Sort by fitness (lower is better)
        population.sort(key=lambda c: c.fitness)
        best_ever = population[0].copy()

        if self.verbose:
            print(f"Initial best fitness: {best_ever.fitness:.2f}")

        # Evolution loop
        no_improvement = 0
        for gen in range(self.generations):
            # Create new population
            new_population = []

            # Elitism: keep best individuals
            for i in range(self.elitism):
                new_population.append(population[i].copy())

            # Generate rest of population
            while len(new_population) < self.population_size:
                # Selection
                parent1 = self._tournament_select(population)
                parent2 = self._tournament_select(population)

                # Crossover
                if random.random() < self.crossover_rate:
                    child1, child2 = self._crossover(parent1, parent2)
                else:
                    child1, child2 = parent1.copy(), parent2.copy()

                # Mutation
                self._mutate(child1)
                self._mutate(child2)

                # Evaluate and add to new population
                child1.fitness = self._evaluate_fitness(child1)
                child2.fitness = self._evaluate_fitness(child2)

                new_population.append(child1)
                if len(new_population) < self.population_size:
                    new_population.append(child2)

            # Replace population
            population = new_population
            population.sort(key=lambda c: c.fitness)

            # Track best and calculate metrics
            current_best = population[0]
            improved = current_best.fitness < best_ever.fitness

            if improved:
                best_ever = current_best.copy()
                no_improvement = 0
            else:
                no_improvement += 1

            # Progress logging (every 5 generations or on improvement)
            if self.verbose and (gen % 5 == 0 or improved or gen == self.generations - 1):
                # Calculate demand % for best solution
                try:
                    temp_solution = self._chromosome_to_solution(best_ever)
                    demand_pct = get_demand_fulfillment_pct(temp_solution)
                    changeover_penalty, changeover_breakdown = objective_changeover_with_timing(temp_solution)
                    total_changeovers = sum(changeover_breakdown.values())

                    demand_status = "✅" if demand_pct >= 100 else "❌"
                    improvement_marker = "🎯" if improved else ""

                    print(f"[GA] Gen {gen+1:3d}/{self.generations} | "
                          f"Fitness: {best_ever.fitness:8.1f} | "
                          f"Demand: {demand_pct:5.1f}% {demand_status} | "
                          f"Changeovers: {total_changeovers} {improvement_marker}")
                except Exception:
                    print(f"[GA] Gen {gen+1:3d}/{self.generations} | "
                          f"Fitness: {best_ever.fitness:8.1f}")

            # Call progress callback if specified
            if self.progress_callback:
                try:
                    temp_solution = self._chromosome_to_solution(best_ever)
                    demand_pct = get_demand_fulfillment_pct(temp_solution)
                    self.progress_callback(gen + 1, self.generations, best_ever.fitness, demand_pct)
                except Exception:
                    self.progress_callback(gen + 1, self.generations, best_ever.fitness, 0.0)

            # Early stopping if no improvement
            if no_improvement >= 20:
                if self.verbose:
                    print(f"[GA] Converged at generation {gen+1} (no improvement for 20 generations)")
                break

        # Convert best chromosome to solution
        solution = self._chromosome_to_solution(best_ever)

        elapsed = time.time() - start_time

        if self.verbose:
            print()
            print("=" * 60)
            print("OPTIMIZATION COMPLETE")
            print("=" * 60)
            print(f"Time: {elapsed:.2f}s")
            print(f"Best fitness: {best_ever.fitness:.2f}")
            is_feasible, _ = validate_solution(solution, verbose=False)
            print(f"Feasible: {'✓' if is_feasible else '✗'}")
            print(f"Total units: {solution.get_total_units():,}")
            print(f"Makespan: {solution.get_makespan_hours():.1f} hours")

        return solution

    def _initialize_population(self) -> list[Chromosome]:
        """Create initial population with mix of random and heuristic solutions."""
        population = []

        # Add some greedy-based solutions
        # Note: We implement a mini-greedy logic here or import it.
        # Ideally import, but to keep 'genetic.py' self-contained if we move things,
        # let's just use the internal _create_greedy_chromosome which duplicates logic slightly
        # OR fix the import.
        # Actually genetic.py has _create_greedy_chromosome() implemented inside it (lines 255+).
        # So it DOES NOT import greedy.py.
        # Let's check lines 209-221.

        for _ in range(max(1, self.population_size // 10)):
            population.append(self._create_greedy_chromosome())

        # Add random solutions
        while len(population) < self.population_size:
            population.append(self._create_random_chromosome())

        return population

    def _create_random_chromosome(self) -> Chromosome:
        """Create a random chromosome."""
        genes = []
        order = 0

        for sku in self.params.skus:
            compatible = self._compatible_lines.get(sku.sku_id, [])
            if not compatible:
                continue

            # Filter compatible lines to ensure they have > 0 speed (double check)
            valid_lines = [lid for lid in compatible if self.params.get_line(lid).get_speed_for_sku(sku.sku_id) > 0]
            if not valid_lines:
                continue

            remaining = max(0, sku.demand_units - sku.starting_stock)

            while remaining > 0:
                line_id = random.choice(valid_lines)

                # Determine batch size (respect min_batch_size)
                min_batch = sku.min_batch_size

                # Random units between min and whatever is left (bounded)
                if remaining <= min_batch:
                   units = remaining # Take all if less than min
                   # But if strict min_batch is required, we should force min_batch
                   units = max(units, min_batch)
                else:
                   units = random.randint(min_batch, remaining)

                genes.append(Gene(
                    sku_id=sku.sku_id,
                    line_id=line_id,
                    units=units,
                    order=order
                ))
                order += 1
                remaining -= units


        # Shuffle order
        random.shuffle(genes)
        for i, gene in enumerate(genes):
            gene.order = i

        return Chromosome(genes=genes)

    def _create_greedy_chromosome(self) -> Chromosome:
        """
        Create a chromosome using CHANGEOVER-AWARE greedy heuristic.

        Strategy:
        1. Group SKUs by "family" (same compatible lines = low changeover)
        2. Assign entire families to the fastest compatible line
        3. This minimizes changeovers by keeping similar SKUs together

        Returns:
            Chromosome with grouped SKU assignments
        """
        genes = []
        order = 0

        # Process families (groups of SKUs with same compatible lines)
        for family_lines, family_skus in self._sku_families.items():
            if not family_lines:  # No compatible lines
                continue

            # Find the fastest line for this family
            best_line = None
            best_avg_speed = 0

            for line_id in family_lines:
                line = self.params.get_line(line_id)
                # Calculate average speed across all SKUs in family
                speeds = [line.get_speed_for_sku(sku.sku_id) for sku in family_skus]
                avg_speed = sum(speeds) / len(speeds) if speeds else 0

                if avg_speed > best_avg_speed:
                    best_avg_speed = avg_speed
                    best_line = line_id

            if best_line is None:
                continue

            # Assign all SKUs in this family to the best line (keeps family together!)
            for sku in family_skus:
                remaining = max(0, sku.demand_units - sku.starting_stock)

                while remaining > 0:
                    line = self.params.get_line(best_line)
                    max_batch = int(line.get_speed_for_sku(sku.sku_id) * line.max_continuous_hours)
                    units = min(max(sku.min_batch_size, max_batch), remaining)

                    genes.append(Gene(sku.sku_id, best_line, units, order))
                    order += 1
                    remaining -= units

        # If some SKUs weren't assigned (e.g., unique compatible lines), handle them
        assigned_skus = set(g.sku_id for g in genes)
        for sku in self.params.skus:
            if sku.sku_id in assigned_skus:
                continue

            compatible = self._compatible_lines.get(sku.sku_id, [])
            if not compatible:
                continue

            remaining = max(0, sku.demand_units - sku.starting_stock)
            while remaining > 0:
                # Pick fastest compatible line
                best_line = None
                best_speed = 0
                for line_id in compatible:
                    line = self.params.get_line(line_id)
                    speed = line.get_speed_for_sku(sku.sku_id)
                    if speed > best_speed:
                        best_speed = speed
                        best_line = line_id

                if best_line is None:
                    break

                line = self.params.get_line(best_line)
                max_batch = int(line.get_speed_for_sku(sku.sku_id) * line.max_continuous_hours)
                units = min(max(sku.min_batch_size, max_batch), remaining)

                genes.append(Gene(sku.sku_id, best_line, units, order))
                order += 1
                remaining -= units

        return Chromosome(genes=genes)

    def _evaluate_fitness(self, chromosome: Chromosome) -> float:
        """
        Evaluate fitness of a chromosome (lower is better).

        Uses quick feasibility pre-check to skip obviously bad solutions.
        """
        # Quick feasibility pre-check (saves ~20% computation)
        if not self._quick_feasibility_check(chromosome):
            return PENALTY_INFEASIBLE_SOLUTION

        try:
            solution = self._chromosome_to_solution(chromosome)

            # Use weighted objective (includes hard demand constraint)
            fitness = objective_weighted(solution)

            # Add penalty for other infeasibilities
            if fitness < PENALTY_INFEASIBLE_SOLUTION:  # Not already penalized
                is_feasible, violations = validate_solution(solution, verbose=False)
                if not is_feasible:
                    fitness += 10000 * len(violations)

            return fitness

        except Exception:
            # Return high penalty for invalid chromosomes
            return float('inf')

    def _chromosome_to_solution(self, chromosome: Chromosome) -> ScheduleSolution:
        """Convert chromosome to ScheduleSolution, splitting batches cleanly across downtimes."""
        line_genes: dict[str, list[Gene]] = {
            line.line_id: [] for line in self.params.lines
        }

        for gene in sorted(chromosome.genes, key=lambda g: g.order):
            if gene.line_id in line_genes:
                line_genes[gene.line_id].append(gene)

        horizon_hours = float(self.params.planning_horizon_days) * 24.0
        horizon_end = self.params.start_date + timedelta(hours=horizon_hours)

        line_solutions = []
        block_counter = 0

        for line in self.params.lines:
            blocks: list[ProductionBlock] = []
            current_offset = 0.0
            last_sku: str | None = None
            uptime_windows = self._uptime_windows.get(line.line_id, [(0.0, horizon_hours)])
            max_cont_hours = (
                line.max_continuous_hours
                if (line.max_continuous_hours and line.max_continuous_hours > 0)
                else horizon_hours
            )
            cleaning_hours = max(0.0, line.cleaning_time_minutes / 60.0)

            for gene in line_genes[line.line_id]:
                speed = line.get_speed_for_sku(gene.sku_id)
                if speed <= 0 or gene.units <= 0:
                    continue

                sku = self.params.get_sku(gene.sku_id)
                remaining_units = gene.units

                while remaining_units > 0:
                    # Locate next uptime window after current_offset
                    slot_found = False
                    for w_start, w_end in uptime_windows:
                        if w_end <= current_offset + 1e-6:
                            continue

                        slot_start = max(current_offset, w_start)
                        changeover_min = 0.0
                        if last_sku is not None and last_sku != gene.sku_id:
                            changeover_min = self.params.get_changeover_time(
                                line.line_id, last_sku, gene.sku_id
                            )
                        changeover_hours = changeover_min / 60.0
                        available_after_co = w_end - slot_start - changeover_hours

                        if available_after_co <= 1e-6:
                            current_offset = w_end
                            continue

                        max_run_hours = min(available_after_co, max_cont_hours)
                        max_units_here = int(max_run_hours * speed)
                        min_chunk = min(sku.min_batch_size, remaining_units)

                        if max_units_here < min_chunk:
                            current_offset = w_end
                            continue

                        if remaining_units <= max_units_here:
                            chunk = remaining_units
                        else:
                            remainder = remaining_units - max_units_here
                            if 0 < remainder < sku.min_batch_size:
                                adjusted_chunk = remaining_units - sku.min_batch_size
                                if adjusted_chunk >= min_chunk:
                                    chunk = adjusted_chunk
                                elif slot_start > w_start + 1e-6:
                                    # Wait for the next full window rather than splitting below min_batch_size
                                    current_offset = w_end
                                    continue
                                else:
                                    chunk = max_units_here
                            else:
                                chunk = max_units_here

                        prod_hours = chunk / speed
                        total_hours = changeover_hours + prod_hours
                        start_dt = self.params.start_date + timedelta(hours=slot_start)
                        end_dt = start_dt + timedelta(hours=total_hours)

                        if end_dt > horizon_end:
                            break

                        block_counter += 1
                        blocks.append(
                            ProductionBlock(
                                block_id=f"GA-BLOCK-{block_counter:04d}",
                                line_id=line.line_id,
                                sku_id=gene.sku_id,
                                start_time=start_dt,
                                end_time=end_dt,
                                units_produced=chunk,
                                changeover_from=last_sku,
                                changeover_time_minutes=changeover_min,
                            )
                        )

                        remaining_units -= chunk
                        last_sku = gene.sku_id
                        current_offset = slot_start + total_hours

                        # Insert cleaning break if split inside the same uptime window due to max_continuous_hours
                        if remaining_units > 0 and current_offset < w_end - 1e-6:
                            current_offset += cleaning_hours

                        slot_found = True
                        break

                    if not slot_found:
                        break

            line_solutions.append(
                LineSolution(
                    line_id=line.line_id,
                    production_blocks=blocks,
                )
            )

        return ScheduleSolution(
            line_solutions=line_solutions,
            params=self.params,
        )

    def _tournament_select(self, population: list[Chromosome]) -> Chromosome:
        """Select individual using tournament selection."""
        tournament = random.sample(population, min(self.tournament_size, len(population)))
        return min(tournament, key=lambda c: c.fitness).copy()

    def _crossover(self, parent1: Chromosome, parent2: Chromosome) -> tuple[Chromosome, Chromosome]:
        """Perform order crossover (OX) on two parents."""
        if len(parent1.genes) == 0 or len(parent2.genes) == 0:
            return parent1.copy(), parent2.copy()

        # Create children by mixing line assignments
        child1_genes = []
        child2_genes = []

        # Build genes for child1: take structure from parent1, some line assignments from parent2
        for gene in parent1.genes:
            new_gene = Gene(gene.sku_id, gene.line_id, gene.units, gene.order)

            # 50% chance to take line assignment from parent2
            if random.random() < 0.5:
                # Find same SKU gene in parent2
                for g2 in parent2.genes:
                    if g2.sku_id == gene.sku_id:
                        if g2.line_id in self._compatible_lines.get(gene.sku_id, []):
                            new_gene.line_id = g2.line_id
                        break

            child1_genes.append(new_gene)

        # Similar for child2
        for gene in parent2.genes:
            new_gene = Gene(gene.sku_id, gene.line_id, gene.units, gene.order)

            if random.random() < 0.5:
                for g1 in parent1.genes:
                    if g1.sku_id == gene.sku_id:
                        if g1.line_id in self._compatible_lines.get(gene.sku_id, []):
                            new_gene.line_id = g1.line_id
                        break

            child2_genes.append(new_gene)

        return Chromosome(genes=child1_genes), Chromosome(genes=child2_genes)

    def _mutate(self, chromosome: Chromosome) -> None:
        """Apply mutations to a chromosome."""
        for gene in chromosome.genes:
            if random.random() < self.mutation_rate:
                mutation_type = random.choice(['line', 'units', 'order'])

                if mutation_type == 'line':
                    # Change line assignment
                    compatible = self._compatible_lines.get(gene.sku_id, [])
                    if len(compatible) > 1:
                        new_line = random.choice([line_opt for line_opt in compatible if line_opt != gene.line_id])
                        gene.line_id = new_line

                elif mutation_type == 'units':
                    # Adjust batch size
                    sku = self.params.get_sku(gene.sku_id)
                    if sku:
                        delta = random.randint(-sku.min_batch_size, sku.min_batch_size)
                        gene.units = max(sku.min_batch_size, gene.units + delta)

                elif mutation_type == 'order':
                    # Swap order with another gene
                    if len(chromosome.genes) > 1:
                        other = random.choice(chromosome.genes)
                        gene.order, other.order = other.order, gene.order


# ========================================
# Convenience Function
# ========================================

def run_genetic_optimization(
    params: ProductionParams,
    population_size: int = 50,
    generations: int = 100,
    verbose: bool = True
) -> ScheduleSolution:
    """
    Run genetic algorithm optimization and return the solution.

    Args:
        params: Production parameters
        population_size: Number of individuals
        generations: Maximum generations
        verbose: Print progress

    Returns:
        ScheduleSolution: Optimized schedule
    """
    optimizer = GeneticOptimizer(
        params,
        population_size=population_size,
        generations=generations,
        verbose=verbose
    )
    return optimizer.solve()
