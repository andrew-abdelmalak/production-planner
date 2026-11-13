"""
Supply Chain Planner - Desktop Application

Main entry point for the PySide6 desktop application.
"""

import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.main_window import MainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('supply_chain_planner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Launch the Supply Chain Planner desktop application."""
    logger.info("Starting Supply Chain Planner application...")
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Supply Chain Planner")
    app.setOrganizationName("Optimization Project")
    
    logger.info("Qt application initialized")
    
    # Apply dark theme
    app.setStyle("Fusion")
    
    logger.info("Creating main window...")
    window = MainWindow()
    window.show()
    
    logger.info("Main window shown, starting event loop...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
