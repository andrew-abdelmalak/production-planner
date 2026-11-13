"""
main_window.py - Main Application Window

The main window with:
- Toolbar (Run, Export, Load)
- Config panel (left)
- Gantt chart (center)
- Metrics panel (right)
- Log panel (bottom) for status messages
"""

import os
import sys
import json
import logging
import traceback
from io import StringIO
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QPushButton, QProgressBar, QLabel,
    QFileDialog, QMessageBox, QSplitter, QStatusBar,
    QTextEdit, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont, QTextCursor

from app.widgets.config_panel import ConfigPanel
from app.widgets.gantt_chart import GanttChartWidget
from app.widgets.metrics_panel import MetricsPanel

logger = logging.getLogger(__name__)


class OptimizationWorker(QThread):
    """Background worker for running optimization."""
    progress = Signal(float, str)  # percent, message
    log_message = Signal(str)  # log text
    finished = Signal(object, object)  # solution, history
    error = Signal(str, str)  # error message, full traceback
    
    def __init__(self, params):
        super().__init__()
        self.params = params
        logger.info("OptimizationWorker initialized")
    
    def run(self):
        logger.info("Optimization worker thread started")
        try:
            from optimizer.ensemble import run_ensemble_optimization, OptimizationProgress
            from core.objectives import get_demand_fulfillment_pct
            from core.constraints import validate_solution
            
            self.log_message.emit("Starting optimization...")
            self.log_message.emit(f"Lines: {len(self.params.lines)}")
            self.log_message.emit(f"SKUs: {len(self.params.skus)}")
            
            logger.info(f"Running optimization with {len(self.params.lines)} lines and {len(self.params.skus)} SKUs")
            
            # Calculate total demand
            total_demand = sum(s.demand_units for s in self.params.skus)
            total_stock = sum(s.starting_stock for s in self.params.skus)
            self.log_message.emit(f"Total demand: {total_demand:,} units")
            self.log_message.emit(f"Starting stock: {total_stock:,} units")
            self.log_message.emit(f"Net to produce: {total_demand - total_stock:,} units")
            self.log_message.emit("-" * 40)
            
            logger.info(f"Total demand: {total_demand}, Stock: {total_stock}, Net: {total_demand - total_stock}")
            
            def on_progress(p: OptimizationProgress):
                self.progress.emit(p.percent_complete, p.message)
                if p.message:
                    msg = f"[{p.percent_complete:.0f}%] {p.message}"
                    self.log_message.emit(msg)
                    logger.debug(msg)
            
            solution, history = run_ensemble_optimization(
                self.params,
                progress_callback=on_progress,
                verbose=False
            )
            
            logger.info(f"Optimization completed, solution: {solution}")
            
            # Log results
            self.log_message.emit("-" * 40)
            if history.best_ever:
                best = history.best_ever
                self.log_message.emit(f"✓ Best fitness: {best.fitness:.1f}")
                self.log_message.emit(f"✓ Demand fulfilled: {best.demand_pct:.1f}%")
                self.log_message.emit(f"✓ Changeovers: {best.total_changeovers}")
                
                logger.info(f"Best solution - Fitness: {best.fitness:.1f}, Demand: {best.demand_pct:.1f}%, Changeovers: {best.total_changeovers}")
                
                # Validate
                is_valid, violations = validate_solution(solution, verbose=False)
                if is_valid:
                    self.log_message.emit("✓ Solution is VALID")
                    logger.info("Solution is valid")
                else:
                    self.log_message.emit(f"⚠ Solution has issues: {len(violations)} violations")
                    logger.warning(f"Solution has {len(violations)} violations")
                    for v in violations[:3]:
                        self.log_message.emit(f"  - {v}")
                        logger.warning(f"  - {v}")
            
            self.finished.emit(solution, history)
            logger.info("Optimization worker finished successfully")
            
        except Exception as e:
            logger.error(f"Optimization failed: {e}", exc_info=True)
            tb = traceback.format_exc()
            self.error.emit(str(e), tb)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        logger.info("Initializing MainWindow")
        self.params = None
        self.solution = None
        self.history = None
        self.worker = None
        
        self._init_ui()
        logger.info("UI initialized")
        self._load_demo_params()
        logger.info("Demo parameters loaded, MainWindow ready")
    
    def _init_ui(self):
        """Initialize the user interface."""
        logger.debug("Starting UI initialization")
        self.setWindowTitle("Supply Chain Planner")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)
        
        # Apply dark theme
        self._apply_dark_theme()
        
        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Toolbar
        self._create_toolbar()
        
        # Content splitter (3 panels)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Config panel
        self.config_panel = ConfigPanel()
        splitter.addWidget(self.config_panel)
        
        # Center: Gantt chart
        self.gantt_chart = GanttChartWidget()
        splitter.addWidget(self.gantt_chart)
        
        # Right: Metrics panel
        self.metrics_panel = MetricsPanel()
        splitter.addWidget(self.metrics_panel)
        
        # Set splitter sizes (20%, 55%, 25%)
        splitter.setSizes([280, 770, 350])
        
        # Vertical splitter for main content and log
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(splitter)
        
        # Log panel at bottom
        log_group = QGroupBox("📋 Optimization Log")
        log_group.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; 
                border: 1px solid #444; 
                border-radius: 4px;
                padding-top: 15px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: none;
            }
        """)
        self.log_text.setPlainText("Ready. Click 'Run Optimization' to start.")
        log_layout.addWidget(self.log_text)
        
        main_splitter.addWidget(log_group)
        main_splitter.setSizes([600, 150])
        
        main_layout.addWidget(main_splitter)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
    def _create_toolbar(self):
        """Create the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Run button
        self.run_btn = QPushButton("▶ Run Optimization")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #666; }
        """)
        self.run_btn.clicked.connect(self._run_optimization)
        toolbar.addWidget(self.run_btn)
        
        toolbar.addSeparator()
        
        # Load config
        load_btn = QPushButton("📂 Load Config")
        load_btn.clicked.connect(self._load_config)
        toolbar.addWidget(load_btn)
        
        # Export schedule
        export_btn = QPushButton("💾 Export Schedule")
        export_btn.clicked.connect(self._export_schedule)
        toolbar.addWidget(export_btn)
        
        toolbar.addSeparator()
        
        # Status label
        self.status_label = QLabel("No schedule loaded")
        toolbar.addWidget(self.status_label)
    
    def _apply_dark_theme(self):
        """Apply dark theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QToolBar {
                background-color: #333;
                border: none;
                padding: 5px;
                spacing: 10px;
            }
            QPushButton {
                background-color: #444;
                border: 1px solid #555;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QSplitter::handle {
                background-color: #444;
                width: 4px;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 3px;
                text-align: center;
                background-color: #333;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
            QStatusBar {
                background-color: #333;
                color: #aaa;
            }
        """)
    
    def _load_demo_params(self):
        """Load demo parameters on startup."""
        try:
            logger.info("Loading demo parameters...")
            from core.params import make_demo_params
            self.params = make_demo_params()
            logger.info(f"Demo params loaded: {len(self.params.lines)} lines, {len(self.params.skus)} SKUs")
            self.config_panel.load_params(self.params)
            self.status_bar.showMessage("Demo configuration loaded")
        except Exception as e:
            logger.error(f"Error loading demo: {e}", exc_info=True)
            self.status_bar.showMessage(f"Error loading demo: {e}")
    
    def _load_config(self):
        """Load configuration from JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Configuration",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                logger.info(f"Loading config from {file_path}")
                from file_io.loader import load_from_json
                self.params = load_from_json(file_path)
                logger.info(f"Config loaded: {len(self.params.lines)} lines, {len(self.params.skus)} SKUs")
                self.config_panel.load_params(self.params)
                self.status_bar.showMessage(f"Loaded: {os.path.basename(file_path)}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to load config:\n{e}")
    
    def _run_optimization(self):
        """Start optimization in background thread."""
        logger.info("Starting optimization run...")
        if self.params is None:
            logger.warning("No configuration loaded")
            QMessageBox.warning(self, "Warning", "No configuration loaded!")
            return
        
        # Clear log and show starting message
        self.log_text.clear()
        self._append_log("=" * 50)
        self._append_log("Starting optimization run...")
        self._append_log("=" * 50)
        
        # Disable UI
        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Optimizing...")
        
        logger.info("Creating optimization worker thread")
        # Start worker
        self.worker = OptimizationWorker(self.params)
        self.worker.progress.connect(self._on_progress)
        self.worker.log_message.connect(self._append_log)
        self.worker.finished.connect(self._on_optimization_finished)
        self.worker.error.connect(self._on_optimization_error)
        self.worker.start()
    
    def _append_log(self, text: str):
        """Append text to the log panel."""
        self.log_text.append(text)
        # Auto-scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
    
    def _on_progress(self, percent, message):
        """Handle progress updates."""
        self.progress_bar.setValue(int(percent))
        self.progress_bar.setFormat(f"{percent:.1f}% - {message}")
        logger.debug(f"Progress: {percent:.1f}% - {message}")
    
    def _on_optimization_finished(self, solution, history):
        """Handle optimization completion."""
        logger.info("Optimization finished successfully")
        self.solution = solution
        self.history = history
        
        # Update UI
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        logger.info("Loading solution into UI panels...")
        # Update panels
        self.gantt_chart.load_solution(solution)
        logger.info("Gantt chart loaded")
        self.metrics_panel.load_solution(solution, history)
        logger.info("Metrics panel loaded")
        
        best = history.best_ever
        status_msg = (
            f"✓ Fitness: {best.fitness:.0f} | "
            f"Demand: {best.demand_pct:.1f}% | "
            f"Changeovers: {best.total_changeovers}"
        )
        self.status_label.setText(status_msg)
        self.status_bar.showMessage("Optimization complete!")
        logger.info(f"Optimization complete: {status_msg}")
    
    def _on_optimization_error(self, error_msg, traceback_str):
        """Handle optimization error."""
        logger.error(f"Optimization failed: {error_msg}\n{traceback_str}")
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # Log the error
        self._append_log("")
        self._append_log("="*50)
        self._append_log("❌ OPTIMIZATION FAILED")
        self._append_log("="*50)
        self._append_log(f"Error: {error_msg}")
        self._append_log("")
        self._append_log("Full traceback:")
        self._append_log(traceback_str)
        
        QMessageBox.critical(
            self, 
            "Optimization Error", 
            f"Optimization failed:\n\n{error_msg}\n\nSee the log panel for details."
        )
        self.status_bar.showMessage("Optimization failed - see log")
    
    def _export_schedule(self):
        """Export schedule to JSON."""
        if self.solution is None:
            QMessageBox.warning(self, "Warning", "No schedule to export!")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Schedule",
            "schedule.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                from file_io.loader import save_solution_to_json
                save_solution_to_json(self.solution, file_path)
                self.status_bar.showMessage(f"Exported: {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export:\n{e}")
