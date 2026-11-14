"""
Supply Chain Planner - Desktop Application

Main entry point for the PySide6 desktop application.
"""

import logging
import sys

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure console logging for interactive GUI execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main():
    """Launch the Supply Chain Planner desktop application."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is required for the desktop GUI. Install with: uv sync --extra gui"
        ) from exc

    from app.main_window import MainWindow

    configure_logging()
    logger.info("Starting Supply Chain Planner application...")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Supply Chain Planner")
    app.setOrganizationName("Production Planner")

    logger.info("Qt application initialized")
    app.setStyle("Fusion")

    logger.info("Creating main window...")
    window = MainWindow()
    window.show()

    logger.info("Main window shown, starting event loop...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
