"""Создание правила прямо из строки таблицы транзакций.

Пользователь выбирает категорию CoinKeeper для операции — здесь строится правило,
которое подхватит и «похожие» операции:
  * по названию операции   — операции с тем же названием (получатель, магазин);
  * по категории банка     — все операции той же категории банка.
Правило записывается в operation_name_rules / vtb_category_rules и действует
при следующей конвертации.
"""
from dataclasses import dataclass
from typing import Any

from .config_manager import CK_INCOME, CK_SAVING, ConfigManager
from .converter import (
    CREDIT_PREFIX, REASON_OWN_TRANSFER, PreviewRow, find_category_rule, find_name_rule,
)

SCOPE_NAME = "name"
SCOPE_CATEGORY = "category"


class RuleError(ValueError):
    """Правило для этой операции и категории построить нельзя."""


@dataclass
class RulePlan:
    scope: str               # SCOPE_NAME | SCOPE_CATEGORY (фактический, после возможного отката на название)
    key: str                 # ключ в operation_name_rules / vtb_category_rules
    base: str                # название или ID категории банка без префикса «доход:»
    rule: dict[str, Any]
    label: str               # человекочитаемое описание области правила
    fell_back_to_name: bool = False   # у операции нет категории банка — правило по названию
    replaces: dict[str, Any] | None = None  # какое правило с этим ключом уже было


def _is_credit(op: dict[str, Any]) -> bool:
    return not op.get("debet", True)


def _name_key(op: dict[str, Any]) -> str:
    name = (op.get("operationName") or op.get("fullOperationName") or "").strip()
    if not name:
        raise RuleError("У операции нет названия — правило по названию создать нельзя")
    return name


def describe_scope(op: dict[str, Any], scope: str) -> tuple[str, str, str, bool]:
    """-> (фактическая область, base, подпись, откат_на_название)."""
    cat = op.get("parentCategory") or {}
    if scope == SCOPE_CATEGORY and cat.get("id") is not None:
        base = str(cat["id"])
        return SCOPE_CATEGORY, base, f"категория банка «{cat.get('name') or base}» ({base})", False
    base = _name_key(op)
    return SCOPE_NAME, base, f"название «{base}»", scope == SCOPE_CATEGORY


def rule_type_for(node_type: int) -> str:
    return "income" if node_type == CK_INCOME else "saving" if node_type == CK_SAVING else "expense"


def plan_rule(op: dict[str, Any], node_id: str, cfg: ConfigManager, scope: str) -> RulePlan:
    node = cfg.nodes().get(node_id)
    if not node:
        raise RuleError(f"Узел {node_id} не найден в конфигурации CoinKeeper")
    if node.get("deleted"):
        raise RuleError(f"«{node.get('name', node_id)}» удалён в CoinKeeper")
    rtype = rule_type_for(node["type"])
    if _is_credit(op) != (rtype == "income"):
        raise RuleError(
            "Для поступления выберите категорию дохода, для списания — расхода, цель или долг"
        )

    used_scope, base, label, fell_back = describe_scope(op, scope)
    key = (CREDIT_PREFIX + base) if _is_credit(op) else base
    rules = cfg.data["operation_name_rules" if used_scope == SCOPE_NAME else "vtb_category_rules"]
    return RulePlan(
        scope=used_scope, key=key, base=base,
        rule={"type": rtype, "cat_id": node_id},
        label=label, fell_back_to_name=fell_back, replaces=rules.get(key),
    )


def apply_plan(cfg: ConfigManager, plan: RulePlan) -> None:
    if plan.scope == SCOPE_NAME:
        cfg.set_name_rule(plan.key, plan.rule)
    else:
        cfg.set_vtb_rule(plan.key, plan.rule)


def would_match(op: dict[str, Any], plan: RulePlan) -> bool:
    """Подпадает ли операция под правило плана (с учётом направления)."""
    probe = {plan.key: plan.rule}
    if plan.scope == SCOPE_NAME:
        return find_name_rule(op, probe) is not None
    return find_category_rule(op, probe) is not None


def count_similar(rows: list[PreviewRow], op: dict[str, Any], scope: str) -> int:
    """Сколько операций из текущей таблицы подпадёт под правило этой области."""
    used_scope, base, _, _ = describe_scope(op, scope)
    key = (CREDIT_PREFIX + base) if _is_credit(op) else base
    probe = RulePlan(used_scope, key, base, {"type": "income" if _is_credit(op) else "expense"}, "")
    return sum(1 for r in rows if r.reason != REASON_OWN_TRANSFER and would_match(r.raw, probe))
