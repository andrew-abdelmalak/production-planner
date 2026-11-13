"""
metrics_panel.py - Metrics Display Panel

Shows optimization results:
- Total units produced
- Demand fulfillment
- Changeovers
- Best fitness
- Run history
"""

from PySide6.QtWidgets import QFrame, QGroupBox, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    """A single metric display card."""

    def __init__(self, title: str, value: str = "—", color: str = "#4CAF50"):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background-color: #333;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(5)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        layout.addWidget(self.value_label)

    def set_value(self, value: str, color: str = None):
        """Update the metric value."""
        self.value_label.setText(value)
        if color:
            self.value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")


class MetricsPanel(QWidget):
    """Right panel for displaying optimization metrics."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title
        title = QLabel("📊 Results")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)

        # Metric cards
        self.fitness_card = MetricCard("Fitness Score", "—", "#4CAF50")
        layout.addWidget(self.fitness_card)

        self.demand_card = MetricCard("Demand Fulfillment", "—", "#2196F3")
        layout.addWidget(self.demand_card)

        self.changeovers_card = MetricCard("Total Changeovers", "—", "#FF9800")
        layout.addWidget(self.changeovers_card)

        self.units_card = MetricCard("Total Units", "—", "#9C27B0")
        layout.addWidget(self.units_card)

        self.time_card = MetricCard("Optimization Time", "—", "#607D8B")
        layout.addWidget(self.time_card)

        # Run history section
        history_group = QGroupBox("📜 Run History")
        history_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
        """)
        self.history_layout = QVBoxLayout(history_group)

        self.history_label = QLabel("No optimization runs yet")
        self.history_label.setStyleSheet("color: #888; padding: 10px;")
        self.history_layout.addWidget(self.history_label)

        layout.addWidget(history_group)

        # Spacer
        layout.addStretch()

    def load_solution(self, solution, history=None):
        """Load solution and history into the panel."""
        if solution is None:
            return

        # Update cards
        if history and history.best_ever:
            best = history.best_ever

            # Fitness
            color = "#4CAF50" if best.fitness < 500 else ("#FF9800" if best.fitness < 1000 else "#f44336")
            self.fitness_card.set_value(f"{best.fitness:.0f}", color)

            # Demand
            color = "#4CAF50" if best.demand_pct >= 100 else ("#FF9800" if best.demand_pct >= 90 else "#f44336")
            self.demand_card.set_value(f"{best.demand_pct:.1f}%", color)

            # Changeovers
            color = "#4CAF50" if best.total_changeovers <= 5 else ("#FF9800" if best.total_changeovers <= 10 else "#f44336")
            self.changeovers_card.set_value(f"{best.total_changeovers}", color)

            # Time
            total_time = sum(r.elapsed_seconds for r in history.runs)
            self.time_card.set_value(f"{total_time:.1f}s")

        # Total units
        total_units = solution.get_total_units()
        self.units_card.set_value(f"{total_units:,}")

        # Update history
        if history:
            self._update_history(history)

    def _update_history(self, history):
        """Update run history display."""
        # Clear old
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add runs
        for run in history.runs[-5:]:  # Show last 5
            is_best = run == history.best_ever
            prefix = "🏆" if is_best else "  "
            text = f"{prefix} Run {run.run_number}: {run.fitness:.0f} ({run.demand_pct:.1f}%)"

            label = QLabel(text)
            label.setStyleSheet(
                "font-weight: bold; color: #4CAF50;" if is_best else "color: #888;"
            )
            self.history_layout.addWidget(label)
