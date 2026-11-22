from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox, QWidget,
)

from core.config_manager import (
    CK_ACCOUNT, CK_EXPENSE, CK_INCOME, CK_SAVING, CK_TYPE_NAMES, ConfigManager,
)


def make_ck_combo(config: ConfigManager, types: tuple[int, ...], current: str = "",
                  allow_empty: bool = True) -> QComboBox:
    """Выпадающий список узлов CoinKeeper нужных типов; userData = ID узла."""
    combo = QComboBox()
    if allow_empty:
        combo.addItem("— не выбрано —", "")
    for ck_id, node in config.get_ck_nodes(types).items():
        combo.addItem(f"{node.get('name', ck_id)}  [{CK_TYPE_NAMES.get(node.get('type'), '?')}]", ck_id)
    idx = combo.findData(current)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo


class AddNodeDialog(QDialog):
    """Добавление счёта / категории / накопления CoinKeeper (ID + название + тип)."""

    def __init__(self, config: ConfigManager, parent: QWidget | None = None,
                 default_type: int = CK_ACCOUNT):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Новый узел CoinKeeper")

        form = QFormLayout(self)
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("ID из CoinKeeper (hex)")
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        for t in (CK_ACCOUNT, CK_EXPENSE, CK_INCOME, CK_SAVING):
            self.type_combo.addItem(CK_TYPE_NAMES[t], t)
        self.type_combo.setCurrentIndex(self.type_combo.findData(default_type))
        form.addRow("ID:", self.id_edit)
        form.addRow("Название:", self.name_edit)
        form.addRow("Тип:", self.type_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self) -> None:
        ck_id = self.id_edit.text().strip()
        if not ck_id:
            QMessageBox.warning(self, "Ошибка", "Укажите ID")
            return
        name = self.name_edit.text().strip() or ck_id
        self.config.add_ck_node(ck_id, name, self.type_combo.currentData())
        self.accept()
