from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from core.config_manager import ConfigManager


class ConfigEditorDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Редактор конфига")
        self.resize(640, 480)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_accounts_tab(), "Счета")
        tabs.addTab(self._build_categories_tab(), "Категории")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

    # --- Счета ---
    def _build_accounts_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.accounts_table = QTableWidget(0, 2)
        self.accounts_table.setHorizontalHeaderLabels(["Счёт", "Отображаемое имя"])
        self.accounts_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.accounts_table)

        row = QHBoxLayout()
        add_btn = QPushButton("Добавить счёт")
        add_btn.clicked.connect(self._add_account)
        del_btn = QPushButton("Удалить выбранный")
        del_btn.clicked.connect(self._delete_account)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch()
        layout.addLayout(row)

        self._refresh_accounts()
        return w

    def _refresh_accounts(self) -> None:
        accounts = self.config.data.get("accounts", {})
        self.accounts_table.setRowCount(len(accounts))
        for row, (acc, name) in enumerate(accounts.items()):
            self.accounts_table.setItem(row, 0, QTableWidgetItem(acc))
            self.accounts_table.setItem(row, 1, QTableWidgetItem(name))

    def _add_account(self) -> None:
        acc, ok = QInputDialog.getText(self, "Новый счёт", "ID счёта:")
        if not ok or not acc.strip():
            return
        name, ok = QInputDialog.getText(self, "Новый счёт", "Отображаемое имя:")
        if not ok:
            return
        self.config.add_account(acc.strip(), name.strip() or acc.strip())
        self._refresh_accounts()

    def _delete_account(self) -> None:
        row = self.accounts_table.currentRow()
        if row < 0:
            return
        acc = self.accounts_table.item(row, 0).text()
        if QMessageBox.question(self, "Удалить", f"Удалить счёт {acc}?") == QMessageBox.StandardButton.Yes:
            self.config.remove_account(acc)
            self._refresh_accounts()

    # --- Категории ---
    def _build_categories_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.categories_list = QListWidget()
        layout.addWidget(self.categories_list)

        row = QHBoxLayout()
        add_btn = QPushButton("Добавить категорию")
        add_btn.clicked.connect(self._add_category)
        del_btn = QPushButton("Удалить выбранную")
        del_btn.clicked.connect(self._delete_category)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch()
        layout.addLayout(row)

        self._refresh_categories()
        return w

    def _refresh_categories(self) -> None:
        self.categories_list.clear()
        self.categories_list.addItems(self.config.get_categories())

    def _add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая категория", "Название:")
        if ok and name.strip():
            self.config.add_category(name.strip())
            self._refresh_categories()

    def _delete_category(self) -> None:
        item = self.categories_list.currentItem()
        if item:
            self.config.remove_category(item.text())
            self._refresh_categories()