from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QTableWidget

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


def fit_columns(table: QTableWidget, wide_col: int | None = None,
                wide_width: int = 380, max_width: int = 480) -> None:
    """Колонки по содержимому, но с возможностью менять ширину вручную.

    Режим Stretch не подходит: такая колонка не тянется мышью, и таблица никогда
    не выходит за ширину окна, поэтому нет горизонтальной прокрутки. Здесь все
    колонки Interactive; если они шире окна — появляется ползунок.
    """
    hdr = table.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    hdr.setStretchLastSection(False)
    hdr.setMinimumSectionSize(50)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.resizeColumnsToContents()
    for col in range(table.columnCount()):
        width = min(table.columnWidth(col), max_width)
        if col == wide_col:
            width = max(width, wide_width)
        table.setColumnWidth(col, width)
