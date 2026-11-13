"""
params.py - Production Scheduling Parameters

Defines the complete problem structure for production scheduling:
- Production lines with capabilities and speeds
- SKUs (products) with demands and priorities
- Changeover matrices (time/cost between SKU pairs)
- Shift definitions and scheduling rules

All parameters are bundled in the ProductionParams dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

# ========================================
# Type Definitions
# ========================================

# SKU pair for changeover lookups: (from_sku, to_sku)
SKUPair = tuple[str, str]


# ========================================
# Production Line Definition
# ========================================

@dataclass
class ProductionLine:
    """
    A single production line with its capabilities.

    Attributes:
        line_id: Unique identifier (e.g., "LINE-A")
        name: Human-readable name (e.g., "Bottling Line 1")
        compatible_skus: List of SKU IDs this line can produce
        base_speed_units_per_hour: Default production rate
        sku_speed_multipliers: Speed varies by SKU (multiplier on base speed)
        max_continuous_hours: Maximum hours before mandatory break
        cleaning_time_minutes: Time required for cleaning between shifts

    Example:
        line = ProductionLine(
            line_id="LINE-A",
            name="Bottling Line 1",
            compatible_skus=["SKU-001", "SKU-002", "SKU-003"],
            base_speed_units_per_hour=1000.0,
            sku_speed_multipliers={"SKU-001": 1.0, "SKU-002": 0.8, "SKU-003": 1.2},
        )
    """
    line_id: str
    name: str
    compatible_skus: list[str]
    base_speed_units_per_hour: float = 1000.0
    sku_speed_multipliers: dict[str, float] = field(default_factory=dict)
    max_continuous_hours: float = 8.0
    cleaning_time_minutes: float = 30.0
    efficiency_percent: float = 100.0
    downtime_windows: list[tuple[float, float]] = field(default_factory=list) # List of (start_hour, end_hour)

    def get_speed_for_sku(self, sku_id: str) -> float:
        """Get production speed (units/hour) for a specific SKU."""
        if sku_id not in self.compatible_skus:
            raise ValueError(f"SKU {sku_id} not compatible with line {self.line_id}")
        multiplier = self.sku_speed_multipliers.get(sku_id, 1.0)
        # Apply efficiency factor: e.g. 91% -> 0.91 multiplier
        return (self.base_speed_units_per_hour * multiplier) * (self.efficiency_percent / 100.0)

    def can_produce(self, sku_id: str) -> bool:
        """Check if this line can produce a given SKU."""
        return sku_id in self.compatible_skus


# ========================================
# SKU (Product) Definition
# ========================================

@dataclass
class SKU:
    """
    A Stock Keeping Unit (product) to be scheduled.

    Attributes:
        sku_id: Unique identifier (e.g., "SKU-001")
        name: Human-readable name (e.g., "500ml Water Bottle")
        demand_units: Total units required to produce
        priority: Priority level (1=highest, higher number=lower priority)
        due_date: Optional deadline for completion
        min_batch_size: Minimum units per production run

    Example:
        sku = SKU(
            sku_id="SKU-001",
            name="500ml Water Bottle",
            demand_units=10000,
            priority=1,
            min_batch_size=500,
        )
    """
    sku_id: str
    name: str
    demand_units: int
    priority: int = 5  # 1=highest priority
    due_date: datetime | None = None
    min_batch_size: int = 100
    starting_stock: int = 0
    underage_buffer_pct: float = 0.0  # Allowable deficit (e.g. 0.10 = allow 90% of demand)
    overage_buffer_pct: float = 0.0   # Allowable excess (e.g. 0.10 = allow 110% of demand)

    def __post_init__(self):
        if self.demand_units < 0:
            raise ValueError(f"Demand must be non-negative, got {self.demand_units}")
        if self.priority < 1:
            raise ValueError(f"Priority must be >= 1, got {self.priority}")
        if self.min_batch_size < 1:
            raise ValueError(f"Min batch size must be >= 1, got {self.min_batch_size}")
        if self.starting_stock < 0:
            raise ValueError(f"Starting stock must be non-negative, got {self.starting_stock}")


# ========================================
# Changeover Matrix
# ========================================

@dataclass
class ChangeoverMatrix:
    """
    Time and cost to switch between SKUs on a specific line.

    Changeover happens when switching production from one SKU to another.
    Different SKU pairs may have different changeover requirements.

    Attributes:
        line_id: Which production line this matrix applies to
        changeover_minutes: Dict mapping (from_sku, to_sku) -> minutes
        changeover_cost: Dict mapping (from_sku, to_sku) -> cost units
        default_minutes: Default changeover time if pair not specified
        default_cost: Default changeover cost if pair not specified

    Example:
        matrix = ChangeoverMatrix(
            line_id="LINE-A",
            changeover_minutes={
                ("SKU-001", "SKU-002"): 30.0,  # Quick change
                ("SKU-002", "SKU-001"): 45.0,  # Slower reverse
            },
            changeover_cost={
                ("SKU-001", "SKU-002"): 100.0,
                ("SKU-002", "SKU-001"): 150.0,
            },
            default_minutes=60.0,
            default_cost=200.0,
        )
    """
    line_id: str
    changeover_minutes: dict[SKUPair, float] = field(default_factory=dict)
    changeover_cost: dict[SKUPair, float] = field(default_factory=dict)
    default_minutes: float = 60.0
    default_cost: float = 100.0

    def get_changeover_time(self, from_sku: str, to_sku: str) -> float:
        """Get changeover time in minutes between two SKUs."""
        if from_sku == to_sku:
            return 0.0  # No changeover needed for same SKU
        return self.changeover_minutes.get((from_sku, to_sku), self.default_minutes)

    def get_changeover_cost(self, from_sku: str, to_sku: str) -> float:
        """Get changeover cost between two SKUs."""
        if from_sku == to_sku:
            return 0.0  # No cost for same SKU
        return self.changeover_cost.get((from_sku, to_sku), self.default_cost)


# ========================================
# Shift Definition
# ========================================

@dataclass
class Shift:
    """
    A production shift period.

    Attributes:
        shift_id: Unique identifier (e.g., "SHIFT-1")
        name: Human-readable name (e.g., "Morning Shift")
        start_time: Shift start time (e.g., 06:00)
        end_time: Shift end time (e.g., 14:00)
        available_lines: List of line IDs operational during this shift
        day_of_week: Optional day index (0=Sunday..6=Saturday); None means every day

    Example:
        shift = Shift(
            shift_id="SHIFT-1",
            name="Morning Shift",
            start_time=time(6, 0),
            end_time=time(14, 0),
            available_lines=["LINE-A", "LINE-B", "LINE-C"],
        )
    """
    shift_id: str
    name: str
    start_time: time
    end_time: time
    available_lines: list[str] = field(default_factory=list)
    day_of_week: int | None = None

    def get_duration_hours(self) -> float:
        """Get shift duration in hours."""
        start_dt = datetime.combine(datetime.today(), self.start_time)
        end_dt = datetime.combine(datetime.today(), self.end_time)

        # Handle overnight shifts
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        return (end_dt - start_dt).total_seconds() / 3600.0

    def is_line_available(self, line_id: str) -> bool:
        """Check if a line is available during this shift."""
        return line_id in self.available_lines

    def matches_date(self, target_date) -> bool:
        """Return True if this shift runs on the given calendar date."""
        if self.day_of_week is None:
            return True
        sunday_first_weekday = (target_date.weekday() + 1) % 7
        return sunday_first_weekday == self.day_of_week


# ========================================
# Weekly Calendar (Day-Specific Scheduling)
# ========================================

@dataclass
class DaySchedule:
    """
    Configuration for a specific day of the week.

    Allows different shifts and rules for different days
    (e.g., Friday only runs second shift).

    Attributes:
        day_of_week: 0=Sunday, 1=Monday, ..., 6=Saturday
        day_name: Human-readable name (e.g., "Friday")
        enabled_shifts: List of shift IDs that operate on this day
        cleaning_minutes: Start-of-day cleaning time
        is_working_day: Whether production runs this day

    Example:
        friday = DaySchedule(
            day_of_week=5,
            day_name="Friday",
            enabled_shifts=["SHIFT-2"],  # Only second shift
            cleaning_minutes=60.0,
            is_working_day=True,
        )
    """
    day_of_week: int
    day_name: str
    enabled_shifts: list[str] = field(default_factory=list)
    cleaning_minutes: float = 60.0
    is_working_day: bool = True

    def has_shift(self, shift_id: str) -> bool:
        """Check if a shift operates on this day."""
        return shift_id in self.enabled_shifts


@dataclass
class WeeklyCalendar:
    """
    Week-level production calendar with day-specific configurations.

    Defines which shifts run on which days, plus changeover/cleaning rules.

    Attributes:
        days: List of 7 DaySchedule objects (Sunday to Saturday)
        changeover_minutes: Default changeover time between SKUs
        cleaning_absorbs_changeover: If True, when changeover happens at
            shift start where cleaning also occurs, time is max(changeover, cleaning)
            not sum. This models the efficiency of doing both together.

    Example:
        calendar = WeeklyCalendar(
            days=[...],  # 7 DaySchedule objects
            changeover_minutes=120.0,
            cleaning_absorbs_changeover=True,
        )
    """
    days: list[DaySchedule] = field(default_factory=list)
    changeover_minutes: float = 120.0
    cleaning_absorbs_changeover: bool = True

    def get_day(self, day_of_week: int) -> DaySchedule | None:
        """Get schedule for a specific day (0=Sunday, 6=Saturday)."""
        for day in self.days:
            if day.day_of_week == day_of_week:
                return day
        return None

    def is_working_day(self, day_of_week: int) -> bool:
        """Check if a given day is a working day."""
        day = self.get_day(day_of_week)
        return day.is_working_day if day else False

    def get_effective_downtime(self, cleaning: float, changeover: float) -> float:
        """
        Calculate effective downtime when cleaning and changeover overlap.

        If cleaning_absorbs_changeover is True, returns max(cleaning, changeover).
        Otherwise returns cleaning + changeover.
        """
        if self.cleaning_absorbs_changeover:
            return max(cleaning, changeover)
        return cleaning + changeover


def make_default_calendar(shift_ids: list[str]) -> WeeklyCalendar:
    """Create a default weekly calendar with all shifts on all days."""
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    days = [
        DaySchedule(
            day_of_week=i,
            day_name=day_names[i],
            enabled_shifts=shift_ids.copy(),
            cleaning_minutes=60.0,
            is_working_day=True,
        )
        for i in range(7)
    ]
    return WeeklyCalendar(days=days, changeover_minutes=120.0)


# ========================================
# Stock and Inventory Management
# ========================================

@dataclass
class StockInfo:
    """
    Inventory information for a SKU.

    Tracks starting stock, safety stock requirements, and buffer percentages
    for inventory planning.

    Attributes:
        sku_id: Which SKU this info is for
        starting_stock: Units available at period start
        safety_stock: Minimum units to maintain (optional, 0 = no requirement)
        buffer_percent: Additional buffer as percentage (0.10 = 10% extra margin)

    Example:
        stock = StockInfo(
            sku_id="SKU-001",
            starting_stock=5000,
            safety_stock=2000,
            buffer_percent=0.10,
        )
    """
    sku_id: str
    starting_stock: int = 0
    safety_stock: int = 0
    buffer_percent: float = 0.0

    def get_net_demand(self, gross_demand: int) -> int:
        """Calculate net demand after considering starting stock."""
        return max(0, gross_demand - self.starting_stock)

    def get_target_production(self, gross_demand: int) -> int:
        """
        Calculate target production considering safety stock and buffer.

        Target = max(0, gross_demand - starting_stock + safety_stock) * (1 + buffer)
        """
        net = self.get_net_demand(gross_demand)
        with_safety = net + self.safety_stock
        with_buffer = int(with_safety * (1 + self.buffer_percent))
        return with_buffer


@dataclass
class SalesDemand:
    """
    Sales demand specification for a SKU.

    Defines demand over a time period. Can be daily, weekly, or monthly.

    Attributes:
        sku_id: Which SKU this demand is for
        period_type: "daily", "weekly", or "monthly"
        demand_per_period: Units demanded per period
        start_date: When this demand starts
        end_date: When this demand ends (None = ongoing)

    Example:
        demand = SalesDemand(
            sku_id="SKU-001",
            period_type="weekly",
            demand_per_period=10000,
            start_date=datetime.now(),
        )
    """
    sku_id: str
    period_type: str  # "daily", "weekly", "monthly"
    demand_per_period: int
    start_date: datetime
    end_date: datetime | None = None

    def get_daily_demand(self) -> float:
        """Convert to daily demand rate."""
        if self.period_type == "daily":
            return float(self.demand_per_period)
        elif self.period_type == "weekly":
            return self.demand_per_period / 7.0
        elif self.period_type == "monthly":
            return self.demand_per_period / 30.0
        else:
            return float(self.demand_per_period)

    def get_demand_for_days(self, num_days: int) -> int:
        """Calculate total demand for a given number of days."""
        return int(self.get_daily_demand() * num_days)


# ========================================
# Complete Production Parameters
# ========================================

@dataclass
class ProductionParams:
    """
    Complete production scheduling parameters.

    This is the main container for all problem data, similar to
    SingleForkParams in the EV routing project.

    Attributes:
        lines: List of production lines
        skus: List of SKUs to schedule
        changeover_matrices: Changeover data per line
        shifts: Shift schedule definitions
        planning_horizon_days: Number of days to schedule
        start_date: Start date of the planning horizon

        # Optimization weights
        w_makespan: Weight for completion time objective
        w_changeover: Weight for changeover cost objective
        w_utilization: Weight for line utilization objective
        w_priority: Weight for respecting SKU priorities
    """
    lines: list[ProductionLine]
    skus: list[SKU]
    changeover_matrices: list[ChangeoverMatrix] = field(default_factory=list)
    shifts: list[Shift] = field(default_factory=list)
    planning_horizon_days: int = 7
    start_date: datetime = field(default_factory=datetime.now)

    # Optimization weights
    w_makespan: float = 1.0
    w_changeover: float = 1.0
    w_utilization: float = 0.5
    w_priority: float = 2.0

    # ========================================
    # Lookup Methods
    # ========================================

    def get_line(self, line_id: str) -> ProductionLine:
        """Get a production line by ID."""
        for line in self.lines:
            if line.line_id == line_id:
                return line
        raise KeyError(f"Line '{line_id}' not found")

    def get_sku(self, sku_id: str) -> SKU:
        """Get a SKU by ID."""
        for sku in self.skus:
            if sku.sku_id == sku_id:
                return sku
        raise KeyError(f"SKU '{sku_id}' not found")

    def get_changeover_matrix(self, line_id: str) -> ChangeoverMatrix | None:
        """Get the changeover matrix for a specific line."""
        for matrix in self.changeover_matrices:
            if matrix.line_id == line_id:
                return matrix
        return None

    def get_changeover_time(self, line_id: str, from_sku: str, to_sku: str) -> float:
        """Get changeover time between SKUs on a line."""
        if from_sku == to_sku:
            return 0.0
        matrix = self.get_changeover_matrix(line_id)
        if matrix is None:
            return 60.0  # Default 60 minutes
        return matrix.get_changeover_time(from_sku, to_sku)

    def get_changeover_cost(self, line_id: str, from_sku: str, to_sku: str) -> float:
        """Get changeover cost between SKUs on a line."""
        if from_sku == to_sku:
            return 0.0
        matrix = self.get_changeover_matrix(line_id)
        if matrix is None:
            return 100.0  # Default cost
        return matrix.get_changeover_cost(from_sku, to_sku)

    def get_compatible_lines(self, sku_id: str) -> list[ProductionLine]:
        """Get all lines that can produce a given SKU."""
        return [line for line in self.lines if line.can_produce(sku_id)]

    def get_total_demand(self) -> int:
        """Get total demand across all SKUs."""
        return sum(sku.demand_units for sku in self.skus)

    def get_working_hours_per_day(self) -> float:
        """Get average working hours per day from shift definitions.

        Returns sum of daily shift durations (or weekly average when shifts specify
        day_of_week), or 24h if no shifts are defined.
        """
        if not self.shifts:
            return 24.0
        if any(s.day_of_week is not None for s in self.shifts):
            weekly_hours = sum(
                s.get_duration_hours() * (1 if s.day_of_week is not None else 7)
                for s in self.shifts
            )
            return weekly_hours / 7.0
        return sum(s.get_duration_hours() for s in self.shifts)

    def get_horizon_hours(self) -> float:
        """Get total planning horizon in working hours (respects shifts)."""
        return self.planning_horizon_days * self.get_working_hours_per_day()

    # ========================================
    # Validation
    # ========================================

    def validate(self) -> None:
        """
        Validate all parameters for consistency.

        Raises:
            ValueError: If any parameter is invalid
        """
        # Check we have lines and SKUs
        if not self.lines:
            raise ValueError("At least one production line required")
        if not self.skus:
            raise ValueError("At least one SKU required")

        # Check line IDs are unique
        line_ids = [line.line_id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Duplicate line IDs found")

        # Check SKU IDs are unique
        sku_ids = [sku.sku_id for sku in self.skus]
        if len(sku_ids) != len(set(sku_ids)):
            raise ValueError("Duplicate SKU IDs found")

        # Check every SKU has at least one compatible line
        for sku in self.skus:
            compatible = self.get_compatible_lines(sku.sku_id)
            if not compatible:
                raise ValueError(
                    f"SKU '{sku.sku_id}' has no compatible production lines"
                )

        # Check changeover matrices reference valid lines
        line_id_set = set(line_ids)
        for matrix in self.changeover_matrices:
            if matrix.line_id not in line_id_set:
                raise ValueError(
                    f"Changeover matrix references unknown line '{matrix.line_id}'"
                )

        # Check shifts reference valid lines
        for shift in self.shifts:
            for line_id in shift.available_lines:
                if line_id not in line_id_set:
                    raise ValueError(
                        f"Shift '{shift.shift_id}' references unknown line '{line_id}'"
                    )

        # Check planning horizon is positive
        if self.planning_horizon_days < 1:
            raise ValueError("Planning horizon must be at least 1 day")


# ========================================
# Factory Function for Demo Instance
# ========================================

def make_demo_params() -> ProductionParams:
    """
    Create a demo instance with 3 lines and 8 SKUs.

    Represents a small beverage bottling factory with:
    - 3 production lines (different speeds/capabilities)
    - 8 SKU products (water, juice, soda variants)
    - 3 shifts per day

    Returns:
        ProductionParams: Fully configured and validated parameters
    """
    # ========================================
    # Production Lines
    # ========================================
    lines = [
        ProductionLine(
            line_id="LINE-A",
            name="High-Speed Bottling Line",
            compatible_skus=["SKU-001", "SKU-002", "SKU-003", "SKU-004"],
            base_speed_units_per_hour=2000.0,
            sku_speed_multipliers={
                "SKU-001": 1.0,   # Water bottles - full speed
                "SKU-002": 0.9,   # Sparkling water - slightly slower
                "SKU-003": 0.85,  # Juice - needs more care
                "SKU-004": 0.8,   # Soda - carbonation
            },
            max_continuous_hours=8.0,
            cleaning_time_minutes=30.0,
        ),
        ProductionLine(
            line_id="LINE-B",
            name="Flexible Multi-Product Line",
            compatible_skus=["SKU-001", "SKU-002", "SKU-003", "SKU-004",
                           "SKU-005", "SKU-006"],
            base_speed_units_per_hour=1200.0,
            sku_speed_multipliers={
                "SKU-001": 1.0,
                "SKU-002": 1.0,
                "SKU-003": 0.9,
                "SKU-004": 0.85,
                "SKU-005": 0.8,   # Large bottles - slower
                "SKU-006": 0.75,  # Premium glass - careful
            },
            max_continuous_hours=6.0,
            cleaning_time_minutes=45.0,
        ),
        ProductionLine(
            line_id="LINE-C",
            name="Specialty Products Line",
            compatible_skus=["SKU-005", "SKU-006", "SKU-007", "SKU-008"],
            base_speed_units_per_hour=800.0,
            sku_speed_multipliers={
                "SKU-005": 1.0,   # Large bottles
                "SKU-006": 0.9,   # Glass premium
                "SKU-007": 0.85,  # Energy drinks
                "SKU-008": 0.8,   # Sports drinks
            },
            max_continuous_hours=8.0,
            cleaning_time_minutes=60.0,  # More thorough cleaning
        ),
    ]

    # ========================================
    # SKUs (Products)
    # ========================================
    skus = [
        SKU("SKU-001", "Water 500ml", demand_units=50000, priority=1, min_batch_size=1000),
        SKU("SKU-002", "Sparkling Water 500ml", demand_units=30000, priority=2, min_batch_size=500),
        SKU("SKU-003", "Orange Juice 1L", demand_units=25000, priority=2, min_batch_size=500),
        SKU("SKU-004", "Cola 500ml", demand_units=40000, priority=1, min_batch_size=1000),
        SKU("SKU-005", "Water 1.5L", demand_units=20000, priority=3, min_batch_size=500),
        SKU("SKU-006", "Premium Glass 750ml", demand_units=10000, priority=4, min_batch_size=200),
        SKU("SKU-007", "Energy Drink 250ml", demand_units=15000, priority=3, min_batch_size=500),
        SKU("SKU-008", "Sports Drink 500ml", demand_units=12000, priority=4, min_batch_size=500),
    ]

    # ========================================
    # Changeover Matrices
    # ========================================
    # Line A changeovers (fast line, quick changes for similar products)
    line_a_matrix = ChangeoverMatrix(
        line_id="LINE-A",
        changeover_minutes={
            ("SKU-001", "SKU-002"): 15.0,  # Water → Sparkling (just carbonation)
            ("SKU-002", "SKU-001"): 20.0,  # Sparkling → Water (flush CO2)
            ("SKU-001", "SKU-003"): 45.0,  # Water → Juice (flavor cleaning)
            ("SKU-003", "SKU-001"): 60.0,  # Juice → Water (thorough clean)
            ("SKU-003", "SKU-004"): 30.0,  # Juice → Soda
            ("SKU-004", "SKU-003"): 40.0,  # Soda → Juice
        },
        changeover_cost={
            ("SKU-001", "SKU-002"): 50.0,
            ("SKU-002", "SKU-001"): 75.0,
            ("SKU-001", "SKU-003"): 150.0,
            ("SKU-003", "SKU-001"): 200.0,
            ("SKU-003", "SKU-004"): 100.0,
            ("SKU-004", "SKU-003"): 125.0,
        },
        default_minutes=45.0,
        default_cost=100.0,
    )

    # Line B changeovers (flexible line, moderate changes)
    line_b_matrix = ChangeoverMatrix(
        line_id="LINE-B",
        default_minutes=60.0,
        default_cost=150.0,
    )

    # Line C changeovers (specialty line, longer changes)
    line_c_matrix = ChangeoverMatrix(
        line_id="LINE-C",
        changeover_minutes={
            ("SKU-007", "SKU-008"): 30.0,  # Energy → Sports (similar)
            ("SKU-008", "SKU-007"): 30.0,
        },
        changeover_cost={
            ("SKU-007", "SKU-008"): 80.0,
            ("SKU-008", "SKU-007"): 80.0,
        },
        default_minutes=75.0,
        default_cost=200.0,
    )

    # ========================================
    # Shifts
    # ========================================
    all_line_ids = [line.line_id for line in lines]
    shifts = [
        Shift(
            shift_id="SHIFT-1",
            name="Morning Shift",
            start_time=time(6, 0),
            end_time=time(14, 0),
            available_lines=all_line_ids,
        ),
        Shift(
            shift_id="SHIFT-2",
            name="Afternoon Shift",
            start_time=time(14, 0),
            end_time=time(22, 0),
            available_lines=all_line_ids,
        ),
        Shift(
            shift_id="SHIFT-3",
            name="Night Shift",
            start_time=time(22, 0),
            end_time=time(6, 0),  # Next day
            available_lines=["LINE-A", "LINE-B"],  # LINE-C not running at night
        ),
    ]

    # ========================================
    # Create and Validate Parameters
    # ========================================
    params = ProductionParams(
        lines=lines,
        skus=skus,
        changeover_matrices=[line_a_matrix, line_b_matrix, line_c_matrix],
        shifts=shifts,
        planning_horizon_days=7,
        start_date=datetime.now().replace(hour=6, minute=0, second=0, microsecond=0),
        w_makespan=1.0,
        w_changeover=1.0,
        w_utilization=0.5,
        w_priority=2.0,
    )

    params.validate()
    return params
