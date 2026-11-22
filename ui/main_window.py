import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from core.config_manager import ConfigManager
from core.converter import ConversionResult
from core.runner import TransformWorker
from core.transformer import TransformResult
from ui.coinkeeper_dialog import CoinKeeperConfigDialog
from ui.config_editor import ConfigEditorDialog
from ui.info_dialog import TransactionInfoDialog
from ui.unknown_dialog import UnknownAccountsDialog
from ui.unmapped_dialog import UnmappedCategoriesDialog

PREVIEW_COLS = ["Дата", "Счёт банка", "Операция", "Сумма", "Тип", "Откуда", "Куда", "Правило"]
KIND_NAMES = {"expense": "расход", "income": "доход", "transfer": "перевод", "saving": "накопление"}
ATTENTION_BG = QBrush(QColor("#fff3cd"))
ATTENTION_FG = QBrush(QColor("#533f03"))


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.worker: TransformWorker | None = None
        self._last_input: Path | None = None
        self._last_output: Path | None = None
        self._last_conversion: ConversionResult | None = None

        self.setWindowTitle("Finance Decoder — банк → CoinKeeper")
        self.resize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addLayout(self._file_row("Входной JSON (выгрузка банка):", "input_edit", self._pick_input))
        layout.addLayout(self._file_row("Выходной JSON (CoinKeeper):", "output_edit", self._pick_output))

        actions = QHBoxLayout()
        self.run_btn = QPushButton("▶ Конвертировать")
        self.run_btn.clicked.connect(self._run_transform)
        edit_btn = QPushButton("⚙ Редактор конфига")
        edit_btn.clicked.connect(self._open_config_editor)
        ck_btn = QPushButton("Конфигурация CoinKeeper")
        ck_btn.setToolTip("Счета, категории, цели и долги CoinKeeper и файл хранения этой конфигурации")
        ck_btn.clicked.connect(self._open_coinkeeper_config)
        self.fix_btn = QPushButton("Настроить операции без правил…")
        self.fix_btn.clicked.connect(self._open_unmapped_dialog)
        self.fix_btn.setEnabled(False)
        self.info_btn = QPushButton("Информация")
        self.info_btn.setToolTip("Исходный объект выбранной операции из файла банка (или двойной клик по строке)")
        self.info_btn.setEnabled(False)
        self.info_btn.clicked.connect(self._open_info)
        actions.addWidget(self.run_btn)
        actions.addWidget(edit_btn)
        actions.addWidget(ck_btn)
        actions.addWidget(self.fix_btn)
        actions.addWidget(self.info_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # --- Сводка ---
        self.summary = QLabel("Выберите файл и нажмите «Конвертировать».")
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        # --- Вкладки результата ---
        self.tabs = QTabWidget()
        self.preview = QTableWidget(0, len(PREVIEW_COLS))
        self.preview.setHorizontalHeaderLabels(PREVIEW_COLS)
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hdr = self.preview.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.preview.itemSelectionChanged.connect(self._update_info_btn)
        self.preview.cellDoubleClicked.connect(lambda *_: self._open_info())

        self.tabs.addTab(self.preview, "Транзакции")

        self.attention = QPlainTextEdit()
        self.attention.setReadOnly(True)
        self.tabs.addTab(self.attention, "Требует внимания")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.tabs.addTab(self.log, "Лог")
        layout.addWidget(self.tabs, 1)

        for w in config.load_warnings + config.ck_store.warnings:
            self._log(f"⚠ {w}")
        for p in config.validate():
            self._log(f"⚠ Конфиг: {p}")

    def _file_row(self, label: str, attr: str, slot) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QLineEdit()
        setattr(self, attr, edit)
        btn = QPushButton("Выбрать…")
        btn.clicked.connect(slot)
        row.addWidget(edit, 1)
        row.addWidget(btn)
        return row

    # --- Вспомогательные ---
    def _log(self, msg: str) -> None:
        self.log.appendPlainText(msg)

    def _pick_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Входной JSON", "", "JSON (*.json);;Все файлы (*)")
        if path:
            self.input_edit.setText(path)
            p = Path(path)
            self.output_edit.setText(str(p.with_name(p.stem + ".out.json")))

    def _pick_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Выходной JSON", "", "JSON (*.json);;Все файлы (*)")
        if path:
            self.output_edit.setText(path)

    def _open_config_editor(self) -> None:
        ConfigEditorDialog(self.config, self).exec()

    def _open_coinkeeper_config(self) -> None:
        dlg = CoinKeeperConfigDialog(self.config, self)
        dlg.exec()
        if dlg.changed:
            n = len(self.config.ck_store.categories)
            self._log(f"✔ Конфигурация CoinKeeper обновлена: {n} объектов ({self.config.ck_store.path})")
            for p in self.config.validate():
                self._log(f"⚠ Конфиг: {p}")

    def _open_unmapped_dialog(self) -> None:
        conv = self._last_conversion
        if not conv:
            return
        if self._resolve_accounts(conv) or self._resolve_categories(conv):
            self._log("✔ Конфиг обновлён. Повторный запуск…")
            self._run_transform()

    # --- Запуск ---
    def _run_transform(self) -> None:
        in_path = Path(self.input_edit.text().strip())
        out_text = self.output_edit.text().strip()

        if not in_path.is_file():
            QMessageBox.warning(self, "Ошибка", "Входной файл не найден")
            return
        if not out_text:
            QMessageBox.warning(self, "Ошибка", "Укажите выходной файл")
            return
        out_path = Path(out_text)
        if out_path.resolve() == in_path.resolve():
            QMessageBox.warning(self, "Ошибка", "Выходной файл совпадает с входным")
            return

        self.run_btn.setEnabled(False)
        self._log(f"→ Конвертация: {in_path}")
        self._last_input, self._last_output = in_path, out_path

        self.worker = TransformWorker(in_path, out_path, self.config)
        self.worker.finished_ok.connect(self._on_transform_done)
        self.worker.failed.connect(self._on_transform_failed)
        self.worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self.worker.start()

    def _on_transform_failed(self, err: str) -> None:
        self._log(f"✖ Ошибка: {err}")
        QMessageBox.critical(self, "Ошибка", err)

    # --- Результат ---
    def _on_transform_done(self, result: TransformResult) -> None:
        conv = result.conversion
        self._last_conversion = conv

        for p in result.config_problems:
            self._log(f"⚠ Конфиг: {p}")
        for err in result.errors:
            self._log(f"⚠ {err}")

        self._show_summary(conv, result)
        self._fill_preview(conv)
        self._fill_attention(conv)
        self.fix_btn.setEnabled(bool(self._accounts_to_resolve(conv) or conv.fallback_groups))

        # Неизвестные счета блокируют запись — разбираем сразу
        if conv.unknown_accounts:
            self._log(f"⚠ Неизвестные счета: {', '.join(conv.unknown_accounts)}")
            if self._resolve_accounts(conv):
                self._log("✔ Конфиг обновлён. Повторный запуск…")
                self._run_transform()
            else:
                self._log("Счета не сопоставлены — выходной файл не сохранён.")
            return

        if result.written:
            self._log(f"✔ Готово: {conv.stats.converted} транзакций → {self._last_output}")
        else:
            self._log("⚠ Выходной файл не записан (нет транзакций или ошибка входных данных).")

    def _show_summary(self, conv: ConversionResult, result: TransformResult) -> None:
        s = conv.stats
        if not s.total:
            self.summary.setText("<b>Нет данных для конвертации.</b>")
            return
        unmatched = sum(g.count for g in conv.unmatched_transfers)
        fallback = sum(g.count for g in conv.fallback_groups)
        parts = [
            f"Операций в файле: <b>{s.total}</b>",
            f"конвертировано: <b>{s.converted}</b>",
            f"дубли переводов: <b>{s.skipped_dups}</b>",
            f"пропущено по правилу: <b>{s.skipped_rules}</b>",
        ]
        line1 = " &nbsp;·&nbsp; ".join(parts)
        if s.gap == 0:
            check = "✅ счётчики сходятся"
        else:
            check = f"<span style='color:#c0392b'>⚠ не попало в результат: <b>{s.gap}</b> (см. «Лог»)</span>"
        extra = []
        if conv.unknown_accounts:
            extra.append(f"<span style='color:#c0392b'>неизвестных счетов: <b>{len(conv.unknown_accounts)}</b></span>")
        if unmatched:
            extra.append(f"переводов без счёта-получателя: <b>{unmatched}</b>")
        if fallback:
            extra.append(f"операций без правила: <b>{fallback}</b>")
        written = (f"💾 файл сохранён: {self._last_output}" if result.written
                   else "<span style='color:#c0392b'>файл не сохранён</span>")
        self.summary.setText("<br>".join(filter(None, [line1, check + ("  ·  " + " · ".join(extra) if extra else ""), written])))

    def _selected_row(self):
        conv = self._last_conversion
        row = self.preview.currentRow()
        if conv and 0 <= row < len(conv.rows):
            return conv.rows[row]
        return None

    def _update_info_btn(self) -> None:
        self.info_btn.setEnabled(self._selected_row() is not None)

    def _open_info(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        title = f"{row.date} · {row.name} · {row.amount:,.2f}".replace(",", " ")
        TransactionInfoDialog(title, json.dumps(row.raw, ensure_ascii=False, indent=2), self).exec()

    def _fill_preview(self, conv: ConversionResult) -> None:
        self.preview.clearSelection()
        self.preview.setRowCount(len(conv.rows))
        for r, row in enumerate(conv.rows):
            cells = [row.date, row.bank_account, row.name, f"{row.amount:,.2f}".replace(",", " "),
                     KIND_NAMES.get(row.kind, row.kind), row.source, row.destination, row.reason]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if row.needs_attention:
                    item.setBackground(ATTENTION_BG)
                    item.setForeground(ATTENTION_FG)
                self.preview.setItem(r, c, item)
        self.preview.resizeColumnsToContents()
        self.preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        n_attn = sum(r.needs_attention for r in conv.rows)
        self.tabs.setTabText(0, f"Транзакции ({len(conv.rows)})")
        self.tabs.setTabText(1, f"Требует внимания ({n_attn})" if n_attn else "Требует внимания")

    def _fill_attention(self, conv: ConversionResult) -> None:
        lines: list[str] = []
        if conv.unknown_accounts:
            lines.append("Счета банка, не сопоставленные со счетами CoinKeeper (account_map):")
            lines += [f"  • {a}" for a in conv.unknown_accounts]
            lines.append("")
        if conv.unmatched_transfers:
            lines.append("Переводы между своими счетами, у которых счёт-получатель не найден в account_map:")
            for g in conv.unmatched_transfers:
                lines.append(f"  [{g.count:>3}×] {g.source_account} → {g.receiver_account}  |  {g.example_name[:40]}")
                lines.append(f"          operationId: {', '.join(g.example_ids)}")
            lines.append("")
        if conv.fallback_groups:
            lines.append("Категории банка без правила (попали в категорию «по умолчанию»):")
            for g in conv.fallback_groups:
                lines.append(f"  [{g.count:>3}×] категория {g.bank_cat_id} «{g.bank_cat_name}» ({g.direction})")
                lines.append(f"          примеры: {', '.join(g.example_names)}")
                lines.append(f"          operationId: {', '.join(g.example_ids)}")
            lines.append("")
        self.attention.setPlainText("\n".join(lines) if lines else "Всё сопоставлено, замечаний нет ✅")

    # --- Диалоги разбора ---
    @staticmethod
    def _accounts_to_resolve(conv: ConversionResult) -> list[str]:
        """Неизвестные счета + счета-получатели переводов, не найденные в конфиге."""
        accounts = list(conv.unknown_accounts)
        for g in conv.unmatched_transfers:
            if g.receiver_account != "неизвестен" and g.receiver_account not in accounts:
                accounts.append(g.receiver_account)
        return accounts

    def _resolve_accounts(self, conv: ConversionResult) -> bool:
        accounts = [a for a in self._accounts_to_resolve(conv) if not self.config.is_known_account(a)]
        if not accounts:
            return False
        dlg = UnknownAccountsDialog(accounts, self.config, self)
        dlg.exec()
        return dlg.added_any

    def _resolve_categories(self, conv: ConversionResult) -> bool:
        if not conv.fallback_groups:
            return False
        dlg = UnmappedCategoriesDialog(conv.fallback_groups, self.config, self)
        dlg.exec()
        return dlg.added_any
