import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from core.config_manager import ConfigManager
from ui.main_window import MainWindow


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config" / "config.json"

    app = QApplication(sys.argv)
    app.setApplicationName("Finance Decoder")

    config = ConfigManager(config_path)
    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())