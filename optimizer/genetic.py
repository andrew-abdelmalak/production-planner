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
from typing import List, Dict, Optional, Tuple, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import random
import copy
import time

from core.params import ProductionParams
from core.solution import ProductionBlock, LineSolution, ScheduleSolution
from core.constraints import validate_solution
from core.objectives import (
    evaluate_solution, 
    objective_weighted, 
    get_demand_fulfillment_pct,
    objective_changeover_with_timing,
)

# Import centralized configuration
from core.config import (
    DEFAULT_POPULATION_SIZE,
    DEFAULT_GENERATIONS,
    DEFAULT_MUTATION_RATE,
    DEFAULT_CROSSOVER_RATE,
    DEFAULT_TOURNAMENT_SIZE,
    DEFAULT_ELITISM,
    PENALTY_INFEASIBLE_SOLUTION,
)


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
    genes: List[Gene]
    fitness: float = float('inf')
    
    def copy(self) -> 'Chromosome':
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
        progress_callback: Optional[Callable[[int, int, float, float], None]] = None
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
        self._calculate_shift_downtimes()
        
        # Pre-compute SKU families for changeover-aware greedy
        self._sku_families = self._group_skus_by_family()

    def _calculate_shift_downtimes(self):
        """Convert shifts into downtime windows for each line."""
        horizon_hours = self.params.planning_horizon_days * 24
        current_date = self.params.start_date.date()
        days_to_check = int(self.params.planning_horizon_days) + 2
        
        for line in self.params.lines:
            if not getattr(line, 'downtime_windows', None):
                line.downtime_windows = []
            
            uptimes = []
            for day_offset in range(days_to_check):
                check_date = current_date + timedelta(days=day_offset)
                for shift in self.params.shifts:
                    if line.line_id not in shift.available_lines:
                        continue
                    
                    start_dt = datetime.combine(check_date, shift.start_time)
                    if shift.end_time < shift.start_time:
                         end_dt = datetime.combine(check_date + timedelta(days=1), shift.end_time)
                    else:
                         end_dt = datetime.combine(check_date, shift.end_time)
                    
                    start_offset = (start_dt - self.params.start_date).total_seconds() / 3600.0
                    end_offset = (end_dt - self.params.start_date).total_seconds() / 3600.0
                    
                    if end_offset > 0:
                        uptimes.append((max(0, start_offset), end_offset))
            
            if not uptimes:
                # No shifts = No availability
                line.downtime_windows.append((0, horizon_hours + 1000))
                continue

            # Merge overlapping uptimes
            uptimes.sort()
            merged_uptimes = []
            if uptimes:
                curr_start, curr_end = uptimes[0]
                for i in range(1, len(uptimes)):
                    next_start, next_end = uptimes[i]
                    if next_start <= curr_end:
                        curr_end = max(curr_end, next_end)
                    else:
                        merged_uptimes.append((curr_start, curr_end))
                        curr_start, curr_end = next_start, next_end
                merged_uptimes.append((curr_start, curr_end))
            
            # Invert to get downtimes
            last_end = 0.0
            for start, end in merged_uptimes:
                if start > last_end:
                    line.downtime_windows.append((last_end, start))
                last_end = max(last_end, end)
            
            # Final downtime
            line.downtime_windows.append((last_end, horizon_hours + 1000))
        
    def _build_compatibility_map(self) -> Dict[str, List[str]]:
        """Build map of SKU -> compatible line IDs."""
        compat = {}
        for sku in self.params.skus:
            compat[sku.sku_id] = [
                line.line_id for line in self.params.lines
                if line.can_produce(sku.sku_id)
            ]
        return compat
    
    def _group_skus_by_family(self) -> Dict[str, List]:
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
                except:
                    print(f"[GA] Gen {gen+1:3d}/{self.generations} | "
                          f"Fitness: {best_ever.fitness:8.1f}")
            
            # Call progress callback if specified
            if self.progress_callback:
                try:
                    temp_solution = self._chromosome_to_solution(best_ever)
                    demand_pct = get_demand_fulfillment_pct(temp_solution)
                    self.progress_callback(gen + 1, self.generations, best_ever.fitness, demand_pct)
                except:
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
    
    def _initialize_population(self) -> List[Chromosome]:
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
                max_batch = max(min_batch, int(remaining * 1.2)) # Allow slightly larger than remaining
                
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
            
        except Exception as e:
            # Return high penalty for invalid chromosomes
            return float('inf')
    
    def _chromosome_to_solution(self, chromosome: Chromosome) -> ScheduleSolution:
        """Convert chromosome to ScheduleSolution."""
        # Group genes by line
        line_genes: Dict[str, List[Gene]] = {
            line.line_id: [] for line in self.params.lines
        }
        
        for gene in sorted(chromosome.genes, key=lambda g: g.order):
            if gene.line_id in line_genes:
                line_genes[gene.line_id].append(gene)
        
        # Calculate horizon end time
        horizon_end = self.params.start_date + timedelta(
            days=self.params.planning_horizon_days
        )
        
        # Build line solutions
        line_solutions = []
        block_counter = 0
        
        for line in self.params.lines:
            blocks = []
            current_time = self.params.start_date
            last_sku = None
            
            for gene in line_genes[line.line_id]:
                block_counter += 1
                
                # Calculate changeover
                changeover = 0.0
                if last_sku is not None and last_sku != gene.sku_id:
                    changeover = self.params.get_changeover_time(
                        line.line_id, last_sku, gene.sku_id
                    )
                
                # Calculate production time
                speed = line.get_speed_for_sku(gene.sku_id)
                if speed <= 0:
                    # Should handle this via penalization or repair, but for now skip
                    continue
                    
                production_hours = gene.units / speed
                
                # Apply Changeover Absorption Logic
                # If the solution implies a Start-of-Day cleaning absorption, we reduce the changeover impact.
                # Since we don't have exact cleaning windows here, we use a heuristic:
                # If changeover is large (> cleaning time) and we just started a shift/day...
                # For now, let's just use the raw changeover but ensure params can handle it if we add logic later.
                
                total_hours = changeover / 60.0 + production_hours
                
                # Check against downtime windows
                # Convert current_time to hours since start
                start_offset = (current_time - self.params.start_date).total_seconds() / 3600.0
                
                effective_start_time = current_time
                
                # Simple collision detection and shift
                if line.downtime_windows:
                    # Sort windows by start time
                    windows = sorted(line.downtime_windows, key=lambda w: w[0])
                    
                    found_slot = False
                    max_iterations = 1000  # Prevent infinite loops
                    iteration = 0
                    
                    while not found_slot and iteration < max_iterations:
                        iteration += 1
                        current_offset = (effective_start_time - self.params.start_date).total_seconds() / 3600.0
                        proposed_end_offset = current_offset + total_hours
                        
                        # HORIZON CHECK: Stop if block would end after horizon
                        proposed_end_time = effective_start_time + timedelta(hours=total_hours)
                        if proposed_end_time > horizon_end:
                            # Cannot fit this block within horizon - skip it
                            break
                        
                        collision = None
                        for w_start, w_end in windows:
                            # Check overlap: (StartA <= EndB) and (EndA >= StartB)
                            if (current_offset < w_end) and (proposed_end_offset > w_start):
                                collision = w_end
                                break
                        
                        if collision is not None:
                            # Jump to end of collision (downtime window)
                            effective_start_time = self.params.start_date + timedelta(hours=collision)
                            # Add a tiny buffer to avoid precision issues
                            effective_start_time += timedelta(minutes=1) 
                        else:
                            found_slot = True
                    
                    # If we couldn't find a valid slot, skip this gene
                    if not found_slot:
                        continue

                # Create block
                end_time = effective_start_time + timedelta(hours=total_hours)
                
                # Final horizon check before adding block
                if end_time > horizon_end:
                    continue  # Skip blocks that extend beyond horizon
                
                blocks.append(ProductionBlock(
                    block_id=f"GA-BLOCK-{block_counter:04d}",
                    line_id=line.line_id,
                    sku_id=gene.sku_id,
                    start_time=effective_start_time,
                    end_time=end_time,
                    units_produced=gene.units,
                    changeover_from=last_sku,
                    changeover_time_minutes=changeover,
                ))
                
                current_time = end_time
                last_sku = gene.sku_id
            
            line_solutions.append(LineSolution(
                line_id=line.line_id,
                production_blocks=blocks,
            ))
        
        return ScheduleSolution(
            line_solutions=line_solutions,
            params=self.params,
        )
    
    def _tournament_select(self, population: List[Chromosome]) -> Chromosome:
        """Select individual using tournament selection."""
        tournament = random.sample(population, min(self.tournament_size, len(population)))
        return min(tournament, key=lambda c: c.fitness).copy()
    
    def _crossover(self, parent1: Chromosome, parent2: Chromosome) -> Tuple[Chromosome, Chromosome]:
        """Perform order crossover (OX) on two parents."""
        if len(parent1.genes) == 0 or len(parent2.genes) == 0:
            return parent1.copy(), parent2.copy()
        
        # Create children by mixing line assignments
        child1_genes = []
        child2_genes = []
        
        # Get all SKU demand requirements
        sku_demand = {sku.sku_id: sku.demand_units for sku in self.params.skus}
        
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
                        new_line = random.choice([l for l in compatible if l != gene.line_id])
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
