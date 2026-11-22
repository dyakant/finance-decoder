from PyQt6.QtWidgets import QComboBox

from core.config_manager import CK_TYPE_NAMES, ConfigManager


def make_ck_combo(config: ConfigManager, types: tuple[int, ...], current: str = "",
                  allow_empty: bool = True) -> QComboBox:
    """Выпадающий список узлов CoinKeeper нужных типов; userData = ID узла.

    Удалённые узлы не предлагаются, кроме уже выбранного (`current`), чтобы
    было видно, что правило ссылается на удалённый узел.
    """
    combo = QComboBox()
    if allow_empty:
        combo.addItem("— не выбрано —", "")
    nodes = config.get_ck_nodes(types)
    if current and current not in nodes:
        cur = config.get_ck_nodes(types, include_deleted=True).get(current)
        if cur:
            nodes = {**nodes, current: cur}
    for ck_id, node in nodes.items():
        label = f"{node.get('name', ck_id)}  [{CK_TYPE_NAMES.get(node.get('type'), '?')}]"
        if node.get("deleted"):
            label += " — удалён"
        combo.addItem(label, ck_id)
    idx = combo.findData(current)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo
