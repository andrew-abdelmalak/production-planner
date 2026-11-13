"""
config_panel.py - Configuration Panel Widget

Displays and allows editing of production parameters:
- Lines (view details)
- SKUs (editable demand)
- Shifts (view schedule)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QGroupBox, QFormLayout, QTreeWidget, QTreeWidgetItem,
    QSpinBox, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class ConfigPanel(QWidget):
    """Left panel for viewing and editing configuration."""
    
    # Signal emitted when config changes
    config_changed = Signal()
    
    def __init__(self):
        super().__init__()
        self.params = None
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("📋 Configuration")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)
        
        # Tabs for different config sections
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; border-radius: 4px; }
            QTabBar::tab { 
                background: #333; 
                padding: 8px 12px; 
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background: #444; }
            QTabBar::tab:hover { background: #555; }
        """)
        
        # SKUs tab (editable)
        self.skus_tab = QWidget()
        self._setup_skus_tab()
        self.tabs.addTab(self.skus_tab, "📦 SKUs")
        
        # Speed Matrix tab (NEW - critical!)
        self.speeds_tab = QWidget()
        self._setup_speeds_tab()
        self.tabs.addTab(self.speeds_tab, "⚡ Speeds")
        
        # Settings tab (NEW - critical!)
        self.settings_tab = QWidget()
        self._setup_settings_tab()
        self.tabs.addTab(self.settings_tab, "⚙️ Settings")
        
        # Lines tab
        self.lines_tab = QWidget()
        self._setup_lines_tab()
        self.tabs.addTab(self.lines_tab, "🏭 Lines")
        
        # Shifts tab
        self.shifts_tab = QWidget()
        self._setup_shifts_tab()
        self.tabs.addTab(self.shifts_tab, "⏰ Shifts")
        
        layout.addWidget(self.tabs)
        
        # Apply changes button
        self.apply_btn = QPushButton("✓ Apply Changes")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #666; color: #888; }
        """)
        self.apply_btn.clicked.connect(self._apply_changes)
        self.apply_btn.setEnabled(False)
        layout.addWidget(self.apply_btn)
    
    def _setup_skus_tab(self):
        """Set up the SKUs tab with editable demand."""
        layout = QVBoxLayout(self.skus_tab)
        
        # Info label
        info = QLabel("Edit demand below, then click 'Apply Changes'")
        info.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        layout.addWidget(info)
        
        # Table for SKUs
        self.sku_table = QTableWidget()
        self.sku_table.setColumnCount(3)
        self.sku_table.setHorizontalHeaderLabels(["SKU Name", "Demand (units)", "Stock"])
        self.sku_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.sku_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sku_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.sku_table.setStyleSheet("""
            QTableWidget { 
                background-color: #333; 
                gridline-color: #444; 
                border: none;
            }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background-color: #4CAF50; }
            QHeaderView::section { 
                background-color: #444; 
                padding: 8px;
                border: none;
                border-right: 1px solid #555;
            }
        """)
        self.sku_table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.sku_table)
    
    def _setup_speeds_tab(self):
        """Set up the Speed Matrix tab - CRITICAL for viewing/editing per-SKU speeds."""
        layout = QVBoxLayout(self.speeds_tab)
        
        # Info label
        info = QLabel("Speed per SKU per Line (units/hr). Red cells (❌) = incompatible. Click to edit.")
        info.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        layout.addWidget(info)
        
        # Speed matrix table: Rows=SKUs, Columns=Lines
        self.speed_table = QTableWidget()
        self.speed_table.setStyleSheet("""
            QTableWidget { 
                background-color: #2a2a2a; 
                gridline-color: #444; 
                border: none;
            }
            QTableWidget::item { padding: 8px; }
            QTableWidget::item:selected { background-color: #4CAF50; }
            QHeaderView::section { 
                background-color: #3a3a3a; 
                padding: 8px;
                border: none;
                border-right: 1px solid #555;
                font-weight: bold;
            }
        """)
        self.speed_table.cellChanged.connect(self._on_speed_cell_changed)
        layout.addWidget(self.speed_table)
    
    def _setup_settings_tab(self):
        """Set up the Settings tab."""
        layout = QVBoxLayout(self.settings_tab)
        info = QLabel("Global settings. Edit and click 'Apply Changes'.")
        info.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        layout.addWidget(info)
        
        form = QFormLayout()
        form.setSpacing(15)
        
        self.horizon_spin = QSpinBox()
        self.horizon_spin.setRange(1, 30)
        self.horizon_spin.setValue(7)
        self.horizon_spin.setSuffix(" days")
        self.horizon_spin.setStyleSheet("QSpinBox { padding: 5px; background: #333; }")
        self.horizon_spin.valueChanged.connect(lambda: self.apply_btn.setEnabled(True))
        form.addRow("📅 Planning Horizon:", self.horizon_spin)
        
        self.changeover_spin = QSpinBox()
        self.changeover_spin.setRange(0, 500)
        self.changeover_spin.setValue(120)
        self.changeover_spin.setSuffix(" min")
        self.changeover_spin.setStyleSheet("QSpinBox { padding: 5px; background: #333; }")
        self.changeover_spin.valueChanged.connect(lambda: self.apply_btn.setEnabled(True))
        form.addRow("🔄 Changeover:", self.changeover_spin)
        
        self.cleaning_spin = QSpinBox()
        self.cleaning_spin.setRange(0, 300)
        self.cleaning_spin.setValue(60)
        self.cleaning_spin.setSuffix(" min")
        self.cleaning_spin.setStyleSheet("QSpinBox { padding: 5px; background: #333; }")
        self.cleaning_spin.valueChanged.connect(lambda: self.apply_btn.setEnabled(True))
        form.addRow("🧹 Cleaning:", self.cleaning_spin)
        
        layout.addLayout(form)
        layout.addStretch()
    
    def _setup_lines_tab(self):
        """Set up the Lines tab."""
        layout = QVBoxLayout(self.lines_tab)
        
        # Scroll area for lines
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        self.lines_layout = QVBoxLayout(content)
        self.lines_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def _setup_shifts_tab(self):
        """Set up the Shifts tab."""
        layout = QVBoxLayout(self.shifts_tab)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        self.shifts_layout = QVBoxLayout(content)
        self.shifts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def _on_cell_changed(self, row, col):
        """Handle cell changes in SKU table."""
        self.apply_btn.setEnabled(True)
    
    def _on_speed_cell_changed(self, row, col):
        """Handle cell changes in Speed Matrix table."""
        self.apply_btn.setEnabled(True)
    
    def _apply_changes(self):
        """Apply changes from the table to params."""
        if not self.params:
            return
        
        try:
            # Update SKU demands from table
            for row in range(self.sku_table.rowCount()):
                # Get demand value
                demand_item = self.sku_table.item(row, 1)
                stock_item = self.sku_table.item(row, 2)
                
                if demand_item:
                    demand_text = demand_item.text().replace(",", "")
                    new_demand = int(demand_text)
                    self.params.skus[row].demand_units = new_demand
                
                if stock_item:
                    stock_text = stock_item.text().replace(",", "")
                    new_stock = int(stock_text)
                    self.params.skus[row].starting_stock = new_stock
            
            # Update speeds from speed matrix
            for row in range(self.speed_table.rowCount()):
                sku = self.params.skus[row]
                for col in range(self.speed_table.columnCount()):
                    line = self.params.lines[col]
                    
                    item = self.speed_table.item(row, col)
                    if not item:
                        continue
                    
                    # Parse speed value
                    text = item.text().strip()
                    if text == "❌" or text == "" or text == "0":
                        new_speed = 0
                    else:
                        try:
                            new_speed = float(text.replace(",", ""))
                        except ValueError:
                            continue
                    
                    # Update line data
                    if new_speed > 0:
                        line.sku_speed_multipliers[sku.sku_id] = new_speed
                        if sku.sku_id not in line.compatible_skus:
                            line.compatible_skus.append(sku.sku_id)
                    else:
                        line.sku_speed_multipliers.pop(sku.sku_id, None)
                        if sku.sku_id in line.compatible_skus:
                            line.compatible_skus.remove(sku.sku_id)
            
            self.apply_btn.setEnabled(False)
            self.config_changed.emit()
            
            QMessageBox.information(
                self, 
                "Changes Applied", 
                "Configuration updated successfully!\nRun optimization to see the new schedule."
            )
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", f"Please enter valid numbers:\n{e}")
    
    def load_params(self, params):
        """Load parameters into the panel."""
        self.params = params
        self.apply_btn.setEnabled(False)
        
        if params is None:
            return
        
        # Populate SKUs table
        self.sku_table.blockSignals(True)
        self.sku_table.setRowCount(len(params.skus))
        
        for i, sku in enumerate(params.skus):
            # Name (read-only)
            name_item = QTableWidgetItem(sku.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.sku_table.setItem(i, 0, name_item)
            
            # Demand (editable)
            demand_item = QTableWidgetItem(f"{sku.demand_units:,}")
            self.sku_table.setItem(i, 1, demand_item)
            
            # Stock (editable)
            stock_item = QTableWidgetItem(f"{sku.starting_stock:,}")
            self.sku_table.setItem(i, 2, stock_item)
        
        self.sku_table.blockSignals(False)
        
        # Populate Speed Matrix
        self.speed_table.blockSignals(True)
        self.speed_table.setRowCount(len(params.skus))
        self.speed_table.setColumnCount(len(params.lines))
        
        # Set headers
        self.speed_table.setVerticalHeaderLabels([sku.name for sku in params.skus])
        self.speed_table.setHorizontalHeaderLabels([line.name for line in params.lines])
        
        # Fill speeds
        for row, sku in enumerate(params.skus):
            for col, line in enumerate(params.lines):
                # Get actual speed from sku_speed_multipliers
                speed = line.sku_speed_multipliers.get(sku.sku_id, 0)
                
                # Create item with color coding
                if speed > 0:
                    item = QTableWidgetItem(f"{speed:,.0f}")
                    item.setBackground(QColor("#004400"))  # Dark green
                    item.setForeground(QColor("#FFFFFF"))  # White text
                else:
                    item = QTableWidgetItem("❌")
                    item.setBackground(QColor("#440000"))  # Dark red
                    item.setForeground(QColor("#888888"))  # Gray text
                
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.speed_table.setItem(row, col, item)
        
        self.speed_table.blockSignals(False)
        
        # Populate Lines
        self._clear_layout(self.lines_layout)
        for line in params.lines:
            card = QGroupBox(f"📌 {line.name}")
            card.setStyleSheet("""
                QGroupBox { 
                    font-weight: bold; 
                    border: 1px solid #444; 
                    border-radius: 4px;
                    margin-top: 10px;
                    padding: 10px;
                    padding-top: 20px;
                }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            """)
            card_layout = QFormLayout(card)
            card_layout.addRow("Speed:", QLabel(f"{line.base_speed_units_per_hour:,.0f} units/hr"))
            card_layout.addRow("Efficiency:", QLabel(f"{line.efficiency_percent:.0f}%"))
            card_layout.addRow("SKUs:", QLabel(f"{len(line.compatible_skus)} compatible"))
            self.lines_layout.addWidget(card)
        
        self.lines_layout.addStretch()
        
        # Populate Shifts
        self._clear_layout(self.shifts_layout)
        for shift in params.shifts:
            card = QGroupBox(f"⏰ {shift.name}")
            card.setStyleSheet("""
                QGroupBox { 
                    font-weight: bold; 
                    border: 1px solid #444; 
                    border-radius: 4px;
                    margin-top: 10px;
                    padding: 10px;
                    padding-top: 20px;
                }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            """)
            card_layout = QFormLayout(card)
            card_layout.addRow("Hours:", QLabel(f"{shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}"))
            card_layout.addRow("Lines:", QLabel(f"{len(shift.available_lines)} available"))
            self.shifts_layout.addWidget(card)
        
        self.shifts_layout.addStretch()
    
    def _clear_layout(self, layout):
        """Clear all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def get_params(self):
        """Get the current (possibly modified) params."""
        return self.params
