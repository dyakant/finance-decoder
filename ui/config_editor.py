from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from core.config_manager import (
    CK_ACCOUNT, CK_DEBT, CK_EXPENSE, CK_INCOME, CK_SAVING, ConfigManager,
)
from ui.widgets import make_ck_combo

# Расход может уходить и в категорию расхода, и в кредит / долг
RULE_CAT_TYPES = {"expense": (CK_EXPENSE, CK_DEBT), "income": (CK_INCOME,), "saving": (CK_SAVING,)}
NO_NODES_HINT = "Нет подходящих узлов. Загрузите конфигурацию в окне «Конфигурация CoinKeeper»."



def _ro(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class ConfigEditorDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Редактор конфига")
        self.resize(820, 540)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_accounts_tab(), "Счета банка")
        self.tabs.addTab(self._build_rules_tab("vtb"), "Правила: категории банка")
        self.tabs.addTab(self._build_rules_tab("name"), "Правила: по названию")
        self.tabs.addTab(self._build_defaults_tab(), "По умолчанию")
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

    # ── общий каркас «таблица + кнопки» ──────────────────────────────────────
    def _table_tab(self, headers: list[str], buttons: list[tuple[str, callable]]):
        w = QWidget()
        layout = QVBoxLayout(w)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(table)
        row = QHBoxLayout()
        for text, slot in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        return w, table

    def _confirm_delete(self, what: str) -> bool:
        return QMessageBox.question(self, "Удалить", f"Удалить {what}?") == QMessageBox.StandardButton.Yes

    # ── Счета банка ──────────────────────────────────────────────────────────
    def _build_accounts_tab(self) -> QWidget:
        w, self.accounts_table = self._table_tab(
            ["Счёт банка", "Счёт CoinKeeper"],
            [("Добавить счёт", self._add_account), ("Удалить выбранный", self._delete_account)],
        )
        self._refresh_accounts()
        return w

    def _refresh_accounts(self) -> None:
        accounts = self.config.data["account_map"]
        self.accounts_table.setRowCount(len(accounts))
        for row, (acc, ck_id) in enumerate(accounts.items()):
            self.accounts_table.setItem(row, 0, _ro(acc))
            self.accounts_table.setItem(row, 1, _ro(self.config.ck_name(ck_id)))

    def _add_account(self) -> None:
        acc, ok = QInputDialog.getText(self, "Новый счёт", "Номер счёта банка (например *0683):")
        if not ok or not acc.strip():
            return
        accounts = self.config.get_ck_nodes((CK_ACCOUNT,))
        if not accounts:
            QMessageBox.information(self, "Нет счетов", NO_NODES_HINT)
            return
        labels = [f"{n['name']} ({cid})" for cid, n in accounts.items()]
        choice, ok = QInputDialog.getItem(self, "Счёт CoinKeeper", "Соответствует:", labels, 0, False)
        if ok:
            self.config.add_account(acc.strip(), list(accounts)[labels.index(choice)])
            self._refresh_accounts()

    def _delete_account(self) -> None:
        row = self.accounts_table.currentRow()
        if row < 0:
            return
        acc = self.accounts_table.item(row, 0).text()
        if self._confirm_delete(f"счёт {acc}"):
            self.config.remove_account(acc)
            self._refresh_accounts()

    # ── Правила (категории банка / по названию) ──────────────────────────────
    def _build_rules_tab(self, kind: str) -> QWidget:
        first = "Категория банка (id)" if kind == "vtb" else "Подстрока в названии"
        w, table = self._table_tab(
            [first, "Тип", "Категория CoinKeeper"],
            [("Добавить правило", lambda: self._add_rule(kind)),
             ("Удалить выбранное", lambda: self._delete_rule(kind))],
        )
        setattr(self, f"{kind}_table", table)
        self._refresh_rules(kind)
        return w

    def _rules(self, kind: str) -> dict:
        return self.config.data["vtb_category_rules" if kind == "vtb" else "operation_name_rules"]

    def _refresh_rules(self, kind: str) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        rules = self._rules(kind)
        table.setRowCount(len(rules))
        for row, (key, rule) in enumerate(rules.items()):
            target = rule.get("cat_id") or ""
            if rule["type"] == "transfer":
                target = f"{self.config.ck_name(rule.get('src_id', ''))} → {self.config.ck_name(rule.get('dst_id', ''))}"
            elif target:
                target = self.config.ck_name(target)
            table.setItem(row, 0, _ro(key))
            table.setItem(row, 1, _ro(rule["type"]))
            table.setItem(row, 2, _ro(target))

    def _add_rule(self, kind: str) -> None:
        prompt = "ID категории банка:" if kind == "vtb" else "Подстрока (без учёта регистра):"
        key, ok = QInputDialog.getText(self, "Новое правило", prompt)
        if not ok or not key.strip():
            return
        rule_type, ok = QInputDialog.getItem(
            self, "Тип правила", "Тип:", ["expense", "income", "saving", "skip"], 0, False
        )
        if not ok:
            return
        rule: dict = {"type": rule_type}
        if rule_type != "skip":
            nodes = self.config.get_ck_nodes(RULE_CAT_TYPES[rule_type])
            if not nodes:
                QMessageBox.information(self, "Нет категорий", NO_NODES_HINT)
                return
            labels = [f"{n['name']} ({cid})" for cid, n in nodes.items()]
            choice, ok = QInputDialog.getItem(self, "Категория CoinKeeper", "Категория:", labels, 0, False)
            if not ok:
                return
            rule["cat_id"] = list(nodes)[labels.index(choice)]
        if kind == "vtb":
            self.config.set_vtb_rule(key.strip(), rule)
        else:
            self.config.set_name_rule(key.strip(), rule)
        self._refresh_rules(kind)

    def _delete_rule(self, kind: str) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        row = table.currentRow()
        if row < 0:
            return
        key = table.item(row, 0).text()
        if self._confirm_delete(f"правило «{key}»"):
            (self.config.remove_vtb_rule if kind == "vtb" else self.config.remove_name_rule)(key)
            self._refresh_rules(kind)

    # ── По умолчанию ─────────────────────────────────────────────────────────
    def _build_defaults_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        d = self.config.data["defaults"]
        self.def_expense = make_ck_combo(self.config, (CK_EXPENSE,), d.get("expense_cat_id", ""))
        self.def_income = make_ck_combo(self.config, (CK_INCOME,), d.get("income_cat_id", ""))
        form.addRow("Расход без правила:", self.def_expense)
        form.addRow("Доход без правила:", self.def_income)
        save = QPushButton("Сохранить")
        save.clicked.connect(lambda: self.config.set_defaults(
            self.def_expense.currentData(), self.def_income.currentData()))
        form.addRow(save)
        return w
