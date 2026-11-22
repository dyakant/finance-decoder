from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.config_manager import CK_EXPENSE, CK_INCOME, CK_SAVING, ConfigManager
from core.converter import FallbackGroup
from ui.widgets import AddNodeDialog, make_ck_combo

COLS = ["Кат. банка", "Название", "Опер.", "Направление", "Примеры", "Категория CoinKeeper"]


class UnmappedCategoriesDialog(QDialog):
    """Категории банка без правила: операции попали в категорию по умолчанию.

    Для каждой группы можно выбрать категорию CoinKeeper — правило запишется
    в vtb_category_rules и применится при повторном запуске.
    """

    def __init__(self, groups: list[FallbackGroup], config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.groups = groups
        self._added_any = False
        self.setWindowTitle("Операции без правила")
        self.resize(900, 460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Эти категории банка не имеют правила и попали в категорию «по умолчанию».\n"
            "Выберите категорию CoinKeeper, чтобы добавить правило (необязательно)."
        ))

        self.table = QTableWidget(len(groups), len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        self._fill_table()

        row = QHBoxLayout()
        new_btn = QPushButton("＋ Новая категория CoinKeeper…")
        new_btn.clicked.connect(self._add_node)
        row.addWidget(new_btn)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton("Сохранить правила", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _types_for(direction: str) -> tuple[int, ...]:
        if direction == "income":
            return (CK_INCOME,)
        if direction == "expense":
            return (CK_EXPENSE, CK_SAVING)
        return (CK_EXPENSE, CK_INCOME, CK_SAVING)

    def _fill_table(self) -> None:
        self.combos = []
        dir_names = {"expense": "расход", "income": "доход", "mixed": "смешанное"}
        for row, g in enumerate(self.groups):
            values = [g.bank_cat_id, g.bank_cat_name, str(g.count),
                      dir_names[g.direction], ", ".join(g.example_names)]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
            combo = make_ck_combo(self.config, self._types_for(g.direction))
            self.table.setCellWidget(row, 5, combo)
            self.combos.append(combo)

    def _add_node(self) -> None:
        if AddNodeDialog(self.config, self, CK_EXPENSE).exec():
            selected = [c.currentData() for c in self.combos]
            self._fill_table()
            for combo, data in zip(self.combos, selected):
                combo.setCurrentIndex(max(combo.findData(data), 0))

    def _save(self) -> None:
        for g, combo in zip(self.groups, self.combos):
            cat_id = combo.currentData()
            if not cat_id:
                continue
            node_type = self.config.data["categories"][cat_id].get("type")
            rule_type = "income" if node_type == CK_INCOME else "saving" if node_type == CK_SAVING else "expense"
            self.config.set_vtb_rule(g.bank_cat_id, {"type": rule_type, "cat_id": cat_id})
            self._added_any = True
        self.accept()

    @property
    def added_any(self) -> bool:
        return self._added_any
