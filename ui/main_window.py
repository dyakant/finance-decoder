from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from core.config_manager import ConfigManager
from core.runner import TransformWorker
from core.transformer import TransformResult
from ui.config_editor import ConfigEditorDialog
from ui.unknown_dialog import UnknownAccountsDialog


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.worker: TransformWorker | None = None
        self._last_input: Path | None = None
        self._last_output: Path | None = None

        self.setWindowTitle("Finance Decoder")
        self.resize(760, 560)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Входной файл ---
        layout.addWidget(QLabel("Входной JSON:"))
        row_in = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Путь к входному файлу…")
        btn_in = QPushButton("Выбрать…")
        btn_in.clicked.connect(self._pick_input)
        row_in.addWidget(self.input_edit)
        row_in.addWidget(btn_in)
        layout.addLayout(row_in)

        # --- Выходной файл ---
        layout.addWidget(QLabel("Выходной JSON:"))
        row_out = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Путь к выходному файлу…")
        btn_out = QPushButton("Выбрать…")
        btn_out.clicked.connect(self._pick_output)
        row_out.addWidget(self.output_edit)
        row_out.addWidget(btn_out)
        layout.addLayout(row_out)

        # --- Кнопки действий ---
        actions = QHBoxLayout()
        self.run_btn = QPushButton("▶ Трансформировать")
        self.run_btn.clicked.connect(self._run_transform)
        edit_btn = QPushButton("⚙ Редактор конфига")
        edit_btn.clicked.connect(self._open_config_editor)
        actions.addWidget(self.run_btn)
        actions.addWidget(edit_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # --- Лог ---
        layout.addWidget(QLabel("Лог:"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

    # --- Вспомогательные ---
    def _log(self, msg: str) -> None:
        self.log.appendPlainText(msg)

    def _pick_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Входной JSON", "", "JSON (*.json);;Все файлы (*)")
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text():
                p = Path(path)
                self.output_edit.setText(str(p.with_name(p.stem + ".out.json")))

    def _pick_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Выходной JSON", "", "JSON (*.json);;Все файлы (*)")
        if path:
            self.output_edit.setText(path)

    def _open_config_editor(self) -> None:
        ConfigEditorDialog(self.config, self).exec()

    # --- Запуск ---
    def _run_transform(self) -> None:
        in_path = Path(self.input_edit.text().strip())
        out_path = Path(self.output_edit.text().strip())

        if not in_path.is_file():
            QMessageBox.warning(self, "Ошибка", "Входной файл не найден")
            return
        if not self.output_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Укажите выходной файл")
            return

        self.run_btn.setEnabled(False)
        self._log(f"→ Запуск трансформации: {in_path}")
        self._last_input, self._last_output = in_path, out_path

        self.worker = TransformWorker(in_path, out_path, self.config)
        self.worker.finished_ok.connect(self._on_transform_done)
        self.worker.failed.connect(self._on_transform_failed)
        self.worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self.worker.start()

    def _on_transform_failed(self, err: str) -> None:
        self._log(f"✖ Ошибка: {err}")
        QMessageBox.critical(self, "Ошибка", err)

    def _on_transform_done(self, result: TransformResult) -> None:
        for err in result.errors:
            self._log(f"⚠ {err}")

        if result.unknown_accounts:
            self._log(f"⚠ Найдены неизвестные счета: {', '.join(result.unknown_accounts)}")
            dlg = UnknownAccountsDialog(result.unknown_accounts, self.config, self)
            dlg.exec()
            if dlg.added_any:
                self._log("✔ Конфиг обновлён. Повторный запуск…")
                self._run_transform()
                return
            else:
                self._log("Счета не добавлены — выходной файл не сохранён.")
                return

        self._log(f"✔ Готово. Файл: {self._last_output}")