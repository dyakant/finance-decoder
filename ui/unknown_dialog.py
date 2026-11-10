from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.config_manager import ConfigManager


class UnknownAccountsDialog(QDialog):
    """Показывает список неизвестных счетов и позволяет добавить их в конфиг."""

    def __init__(self, accounts: list[str], config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Неизвестные счета")
        self.resize(560, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Обнаружены счета, отсутствующие в конфиге. "
            "Укажите отображаемое имя и нажмите «Добавить»."
        ))

        self.table = QTableWidget(len(accounts), 2)
        self.table.setHorizontalHeaderLabels(["Счёт", "Отображаемое имя"])
        self.table.horizontalHeader().setStretchLastSection(True)

        for row, acc in enumerate(accounts):
            acc_item = QTableWidgetItem(acc)
            acc_item.setFlags(acc_item.flags() & ~acc_item.flags().__class__.ItemIsEditable)
            self.table.setItem(row, 0, acc_item)
            self.table.setItem(row, 1, QTableWidgetItem(acc))

        layout.addWidget(self.table)

        add_btn = QPushButton("Добавить отмеченные в конфиг")
        add_btn.clicked.connect(self._add_selected)
        layout.addWidget(add_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._added_any = False

    def _add_selected(self) -> None:
        for row in range(self.table.rowCount()):
            acc = self.table.item(row, 0).text()
            name = self.table.item(row, 1).text().strip() or acc
            if not self.config.is_known_account(acc):
                self.config.add_account(acc, name)
                self._added_any = True
        self.accept()

    @property
    def added_any(self) -> bool:
        return self._added_any