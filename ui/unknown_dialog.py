from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from PyQt6.QtCore import Qt

from core.config_manager import CK_ACCOUNT, ConfigManager
from ui.widgets import make_ck_combo


class UnknownAccountsDialog(QDialog):
    """Счета банка, которых нет в account_map: сопоставляем их со счетами CoinKeeper."""

    def __init__(self, accounts: list[str], config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.accounts = accounts
        self._added_any = False
        self.setWindowTitle("Неизвестные счета")
        self.resize(620, 400)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Эти счета банка не сопоставлены со счетами CoinKeeper.\n"
            "Выберите счёт CoinKeeper для каждого и нажмите «Сохранить в конфиг».\n"
            "Нужного счёта нет в списке? Загрузите свежую конфигурацию в окне «Конфигурация CoinKeeper»."
        ))

        self.table = QTableWidget(len(accounts), 2)
        self.table.setHorizontalHeaderLabels(["Счёт банка", "Счёт CoinKeeper"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self._fill_table()

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton("Сохранить в конфиг", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fill_table(self) -> None:
        self.combos = []
        for row, acc in enumerate(self.accounts):
            item = QTableWidgetItem(acc)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            combo = make_ck_combo(self.config, (CK_ACCOUNT,))
            self.table.setCellWidget(row, 1, combo)
            self.combos.append(combo)

    def _save(self) -> None:
        for acc, combo in zip(self.accounts, self.combos):
            ck_id = combo.currentData()
            if ck_id and not self.config.is_known_account(acc):
                self.config.add_account(acc, ck_id)
                self._added_any = True
        self.accept()

    @property
    def added_any(self) -> bool:
        return self._added_any
