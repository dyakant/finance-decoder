from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .config_manager import ConfigManager
from .transformer import TransformResult, run_transform


class TransformWorker(QThread):
    finished_ok = pyqtSignal(object)      # TransformResult
    failed = pyqtSignal(str)

    def __init__(self, input_path: Path, output_path: Path, config: ConfigManager):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.config = config

    def run(self) -> None:
        try:
            result: TransformResult = run_transform(
                self.input_path, self.output_path, self.config
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")