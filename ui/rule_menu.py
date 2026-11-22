from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import QMenu, QWidget

from core.config_manager import (
    CK_DEBT, CK_EXPENSE, CK_INCOME, CK_SAVING, CK_TYPE_NAMES, ConfigManager,
)
from core.converter import PreviewRow

# Какие типы узлов можно выбрать для списания и для поступления
EXPENSE_TYPES = (CK_EXPENSE, CK_SAVING, CK_DEBT)
INCOME_TYPES = (CK_INCOME,)

SECTION_TITLES = {
    CK_EXPENSE: "Расходы",
    CK_SAVING: "Цели / накопления",
    CK_DEBT: "Кредиты / долги",
    CK_INCOME: "Доходы",
}


def editable_side(row: PreviewRow) -> str | None:
    """Какая сторона строки — «категорийная»: 'destination' у расхода, 'source' у дохода.

    Вторая сторона — ваш счёт (задаётся сопоставлением счетов), а у переводов между
    своими счетами обе стороны счета и правило не нужно.
    """
    if row.kind in ("expense", "saving"):
        return "destination"
    if row.kind == "income":
        return "source"
    return None


def pick_category(parent: QWidget, config: ConfigManager, row: PreviewRow,
                  header: str, current_id: str) -> str | None:
    """Показывает меню категорий у курсора. Возвращает ID выбранного узла или None."""
    types = INCOME_TYPES if row.kind == "income" else EXPENSE_TYPES
    nodes = config.get_ck_nodes(types)
    # текущий узел может быть удалённым — оставляем его в меню, чтобы было видно
    if current_id and current_id not in nodes:
        cur = config.get_ck_nodes(types, include_deleted=True).get(current_id)
        if cur:
            nodes = {**nodes, current_id: cur}

    menu = QMenu(parent)
    title = menu.addAction(header)
    title.setEnabled(False)
    if not nodes:
        empty = menu.addAction("Нет категорий — загрузите конфигурацию CoinKeeper")
        empty.setEnabled(False)

    for t in types:
        group = [(cid, n) for cid, n in nodes.items() if n.get("type") == t]
        if not group:
            continue
        menu.addSeparator()
        section = menu.addAction(f"— {SECTION_TITLES.get(t, CK_TYPE_NAMES.get(t, '?'))} —")
        section.setEnabled(False)
        for cid, n in group:
            label = n.get("name", cid) + (" (удалён)" if n.get("deleted") else "")
            act: QAction = menu.addAction(label)
            act.setData(cid)
            if cid == current_id:
                act.setCheckable(True)
                act.setChecked(True)

    chosen = menu.exec(QCursor.pos())
    return chosen.data() if chosen is not None and chosen.data() else None
