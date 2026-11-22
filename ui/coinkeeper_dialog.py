import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.coinkeeper_config import CKCategory, CoinKeeperFormatError
from core.config_manager import CK_TYPE_NAMES, ConfigManager
from core.ck_types import CK_TYPE_ORDER
from ui.info_dialog import TransactionInfoDialog

COLS = ["Название", "Тип", "Валюта", "Статус", "Сумма", "Лимит", "Иконка", "ID"]


def _fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ") if x else ""


class CoinKeeperConfigDialog(QDialog):
    """Конфигурация CoinKeeper: файл хранения и список счетов, категорий, целей и долгов."""

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.store = config.ck_store
        self.changed = False  # конфигурацию перезагружали из файла
        self.setWindowTitle("Конфигурация CoinKeeper")
        self.resize(1050, 640)

        layout = QVBoxLayout(self)

        # --- Файл хранения ---
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Файл хранения:"))
        self.path_edit = QLineEdit(str(self.store.path))
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit, 1)
        copy_btn = QPushButton("Копировать путь")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(str(self.store.path)))
        path_row.addWidget(copy_btn)
        layout.addLayout(path_row)

        self.file_label = QLabel()
        self.file_label.setTextFormat(Qt.TextFormat.RichText)
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Загрузить из файла CoinKeeper…")
        load_btn.setToolTip("Выбрать выгрузку конфигурации CoinKeeper (JSON) и сохранить её в файл хранения")
        load_btn.clicked.connect(self._import)
        reload_btn = QPushButton("Перечитать файл хранения")
        reload_btn.clicked.connect(self._reload)
        btn_row.addWidget(load_btn)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- Сводка по типам ---
        self.counts_label = QLabel()
        self.counts_label.setTextFormat(Qt.TextFormat.RichText)
        self.counts_label.setWordWrap(True)
        layout.addWidget(self.counts_label)

        # --- Фильтры ---
        filters = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItem("Все типы", None)
        for t in CK_TYPE_ORDER:
            self.type_combo.addItem(CK_TYPE_NAMES[t], t)
        self.deleted_check = QCheckBox("Показывать удалённые")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по названию или ID")
        self.search_edit.setClearButtonEnabled(True)
        filters.addWidget(self.type_combo)
        filters.addWidget(self.deleted_check)
        filters.addWidget(self.search_edit, 1)
        layout.addLayout(filters)
        self.type_combo.currentIndexChanged.connect(self._fill_table)
        self.deleted_check.toggled.connect(self._fill_table)
        self.search_edit.textChanged.connect(self._fill_table)

        # --- Таблица ---
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._show_raw)
        layout.addWidget(self.table, 1)

        self.hint_label = QLabel("Двойной клик по строке — полный объект из конфигурации.")
        layout.addWidget(self.hint_label)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._refresh()

    # --- Данные ---
    def _refresh(self) -> None:
        self._update_header()
        self._fill_table()

    def _update_header(self) -> None:
        info = self.store.file_info()
        if info is None:
            self.file_label.setText(
                "<span style='color:#c0392b'>Файл хранения ещё не создан.</span> "
                "Нажмите «Загрузить из файла CoinKeeper…» и выберите выгрузку конфигурации."
            )
        else:
            size, mtime = info
            total = len(self.store.categories)
            deleted = sum(c.deleted for c in self.store.categories)
            self.file_label.setText(
                f"Файл: {size / 1024:.1f} КБ, изменён {mtime:%d.%m.%Y %H:%M} &nbsp;·&nbsp; "
                f"объектов: <b>{total}</b> (активных {total - deleted}, удалённых {deleted})"
            )
        for w in self.store.warnings:
            self.file_label.setText(self.file_label.text() + f"<br><span style='color:#c0392b'>⚠ {w}</span>")

        counts = self.store.counts()
        parts = []
        for t in CK_TYPE_ORDER:
            active, deleted = counts.get(t, (0, 0))
            parts.append(f"{CK_TYPE_NAMES[t]}: <b>{active}</b>" + (f" <small>(+{deleted} удал.)</small>" if deleted else ""))
        self.counts_label.setText(" &nbsp;·&nbsp; ".join(parts))

    def _visible(self) -> list[CKCategory]:
        t = self.type_combo.currentData()
        show_deleted = self.deleted_check.isChecked()
        q = self.search_edit.text().strip().lower()
        return [
            c for c in self.store.categories
            if (t is None or c.category_type == t)
            and (show_deleted or not c.deleted)
            and (not q or q in c.name.lower() or q in c.id.lower())
        ]

    def _fill_table(self) -> None:
        self._rows = self._visible()
        muted = self.palette().color(QPalette.ColorRole.PlaceholderText)
        self.table.setRowCount(len(self._rows))
        for r, c in enumerate(self._rows):
            cells = [
                c.name.strip(), CK_TYPE_NAMES.get(c.category_type, f"? ({c.category_type})"), c.currency,
                c.status, _fmt(c.amount), _fmt(c.limit_amount), c.icon, c.id,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c.deleted:
                    item.setForeground(muted)
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.hint_label.setText(
            f"Показано: {len(self._rows)} из {len(self.store.categories)}. "
            "Двойной клик по строке — полный объект из конфигурации."
        )

    def _show_raw(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._rows):
            c = self._rows[row]
            TransactionInfoDialog(
                f"{CK_TYPE_NAMES.get(c.category_type, '?')} · {c.name.strip()} · {c.status}",
                json.dumps(c.raw, ensure_ascii=False, indent=2), self,
                window_title="Объект конфигурации CoinKeeper",
            ).exec()

    # --- Действия ---
    def _reload(self) -> None:
        self.store.load()
        self.changed = True
        self._refresh()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Конфигурация CoinKeeper", "", "JSON и текст (*.json *.txt);;Все файлы (*)"
        )
        if not path:
            return
        try:
            diff = self.store.diff_with(path)
        except (CoinKeeperFormatError, OSError) as e:
            QMessageBox.critical(self, "Не удалось прочитать файл", str(e))
            return

        if self.store.categories:
            text = (
                f"В файле {diff.total} объектов. Текущая конфигурация будет заменена:\n"
                f"  + новых: {diff.added}\n  − пропадёт: {diff.removed}\n  ~ изменится: {diff.changed}\n\n"
                "Предыдущая версия сохранится рядом как .bak. Продолжить?"
            )
            if QMessageBox.question(self, "Заменить конфигурацию", text) != QMessageBox.StandardButton.Yes:
                return

        try:
            self.store.import_file(path)
        except (CoinKeeperFormatError, OSError) as e:
            QMessageBox.critical(self, "Ошибка загрузки", str(e))
            return
        self.changed = True
        self._refresh()

        notes = [f"Загружено объектов: {diff.total}."] + [f"⚠ {w}" for w in diff.warnings[:5]]
        problems = [p for p in self.config.validate() if "ID" in p or "удал" in p]
        if problems:
            notes.append("\nПроблемы в текущих настройках:")
            notes += [f"• {p}" for p in problems[:8]]
            if len(problems) > 8:
                notes.append(f"… и ещё {len(problems) - 8}")
        QMessageBox.information(self, "Конфигурация загружена", "\n".join(notes))
