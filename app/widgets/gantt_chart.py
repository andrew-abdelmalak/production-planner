"""
gantt_chart.py - Gantt Chart Visualization Widget

Displays the production schedule as a Gantt chart with:
- Timeline on X axis
- Production lines on Y axis
- Colored blocks for each production run
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

# Color palette for SKUs
SKU_COLORS = [
    "#4CAF50",  # Green
    "#2196F3",  # Blue
    "#FF9800",  # Orange
    "#9C27B0",  # Purple
    "#E91E63",  # Pink
    "#00BCD4",  # Cyan
    "#FFC107",  # Amber
    "#795548",  # Brown
    "#607D8B",  # Blue Grey
    "#8BC34A",  # Light Green
]


class GanttChartCanvas(QWidget):
    """Canvas for drawing the Gantt chart."""

    def __init__(self):
        super().__init__()
        self.solution = None
        self.sku_colors = {}
        self.setMinimumSize(600, 200)
        logger.debug("GanttChartCanvas initialized")

    def load_solution(self, solution):
        """Load solution for visualization."""
        logger.info(f"Loading solution into Gantt chart: {solution}")
        self.solution = solution

        # Assign colors to SKUs
        if solution:
            logger.debug(f"Solution has {len(solution.line_solutions)} lines")
            skus = list(set(
                block.sku_id
                for ls in solution.line_solutions
                for block in ls.production_blocks
            ))
            logger.debug(f"Found {len(skus)} unique SKUs: {skus}")
            self.sku_colors = {
                sku_id: SKU_COLORS[i % len(SKU_COLORS)]
                for i, sku_id in enumerate(sorted(skus))
            }
            logger.info(f"Assigned colors to {len(self.sku_colors)} SKUs")
        else:
            logger.warning("Solution is None or empty")

        # Resize based on content
        if solution and solution.line_solutions:
            height = max(300, len(solution.line_solutions) * 80 + 100)
            self.setMinimumHeight(height)
            logger.debug(f"Set canvas height to {height} for {len(solution.line_solutions)} lines")

        self.update()
        logger.info("Gantt chart updated")

    def paintEvent(self, event):
        """Draw the Gantt chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#2d2d2d"))

        if not self.solution or not self.solution.line_solutions:
            # No data message
            logger.debug("No solution to display")
            painter.setPen(QColor("#888"))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Run optimization to see schedule"
            )
            return

        logger.debug("Painting Gantt chart...")

        # Chart dimensions
        margin_left = 120
        margin_top = 40
        margin_right = 20
        margin_bottom = 40

        chart_width = self.width() - margin_left - margin_right
        chart_height = self.height() - margin_top - margin_bottom

        # Calculate time range
        all_times = []
        for ls in self.solution.line_solutions:
            logger.debug(f"Line {ls.line_id} has {len(ls.production_blocks)} blocks")
            for block in ls.production_blocks:
                all_times.append(block.start_time)
                all_times.append(block.end_time)

        if not all_times:
            logger.warning("No times found in solution blocks")
            return

        min_time = min(all_times)
        max_time = max(all_times)
        time_range = (max_time - min_time).total_seconds() / 3600  # hours
        logger.debug(f"Time range: {min_time} to {max_time}, duration: {time_range} hours")

        if time_range <= 0:
            time_range = 1

        # Row height
        num_lines = len(self.solution.line_solutions)
        row_height = chart_height / max(1, num_lines)

        # Draw title
        painter.setPen(QColor("#fff"))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        painter.drawText(margin_left, 25, "Production Schedule")

        # Draw lines and blocks
        for i, line_sol in enumerate(self.solution.line_solutions):
            y = margin_top + i * row_height

            # Line label
            painter.setPen(QColor("#e0e0e0"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                5, int(y + row_height / 2 + 5),
                line_sol.line_id[:15]
            )

            # Background lane
            painter.fillRect(
                int(margin_left), int(y + 5),
                int(chart_width), int(row_height - 10),
                QColor("#3a3a3a")
            )

            # Draw blocks
            logger.debug(f"Drawing {len(line_sol.production_blocks)} blocks for line {line_sol.line_id}")
            for block in line_sol.production_blocks:
                block_start = (block.start_time - min_time).total_seconds() / 3600
                block_duration = (block.end_time - block.start_time).total_seconds() / 3600

                x = margin_left + (block_start / time_range) * chart_width
                width = max(5, (block_duration / time_range) * chart_width)

                # Block rectangle
                color = QColor(self.sku_colors.get(block.sku_id, "#666"))
                painter.fillRect(
                    int(x), int(y + 8),
                    int(width - 2), int(row_height - 16),
                    color
                )

                # Block border
                painter.setPen(QPen(color.darker(120), 1))
                painter.drawRect(
                    int(x), int(y + 8),
                    int(width - 2), int(row_height - 16)
                )

                # SKU label (if wide enough)
                if width > 50:
                    painter.setPen(QColor("#fff"))
                    painter.setFont(QFont("Segoe UI", 8))
                    label = block.sku_id[-8:] if len(block.sku_id) > 8 else block.sku_id
                    painter.drawText(
                        int(x + 5), int(y + row_height / 2 + 3),
                        label
                    )

        # Draw time axis
        painter.setPen(QColor("#888"))
        painter.setFont(QFont("Segoe UI", 9))

        num_ticks = min(10, int(time_range) + 1)
        for i in range(num_ticks + 1):
            x = margin_left + (i / num_ticks) * chart_width
            hours = (time_range * i / num_ticks)

            painter.drawLine(int(x), int(margin_top + chart_height), int(x), int(margin_top + chart_height + 5))
            painter.drawText(int(x - 15), int(margin_top + chart_height + 20), f"{hours:.0f}h")

        logger.debug("Gantt chart painting completed")


class GanttChartWidget(QWidget):
    """Scrollable Gantt chart widget."""

    def __init__(self):
        super().__init__()
        logger.debug("Initializing GanttChartWidget")
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title
        title = QLabel("📊 Gantt Chart")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)

        # Scroll area for chart
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: 1px solid #444; border-radius: 4px; }
            QScrollBar:vertical { width: 10px; }
            QScrollBar:horizontal { height: 10px; }
        """)

        self.canvas = GanttChartCanvas()
        scroll.setWidget(self.canvas)

        layout.addWidget(scroll)

        # Legend (will be populated when solution loads)
        self.legend_layout = QHBoxLayout()
        self.legend_layout.setSpacing(15)
        layout.addLayout(self.legend_layout)

        logger.info("GanttChartWidget initialized")

    def load_solution(self, solution):
        """Load solution into the chart."""
        logger.info(f"Loading solution in GanttChartWidget: {solution}")
        self.canvas.load_solution(solution)

        # Update legend
        self._update_legend()
        logger.info("Legend updated")

    def _update_legend(self):
        """Update the color legend."""
        # Clear old legend
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.canvas.sku_colors:
            return

        # Add legend items
        for sku_id, color in list(self.canvas.sku_colors.items())[:8]:
            item = QLabel(f"● {sku_id}")
            item.setStyleSheet(f"color: {color}; font-size: 10px;")
            self.legend_layout.addWidget(item)

        self.legend_layout.addStretch()
