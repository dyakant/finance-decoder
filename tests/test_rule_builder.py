import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.config_manager import ConfigManager
from core.converter import convert
from core.rule_builder import (
    SCOPE_CATEGORY, SCOPE_NAME, RuleError, apply_plan, count_similar, plan_rule,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CK = [
    {"id": "acc", "name": "Карта", "categoryType": 2, "deleted": False},
    {"id": "food", "name": "Питание", "categoryType": 3, "deleted": False},
    {"id": "gift", "name": "Подарки", "categoryType": 3, "deleted": False},
    {"id": "inc", "name": "Доход", "categoryType": 1, "deleted": False},
    {"id": "goal", "name": "Подушка", "categoryType": 6, "deleted": False},
    {"id": "debt", "name": "Кредит", "categoryType": 5, "deleted": False},
    {"id": "gone", "name": "Старая", "categoryType": 3, "deleted": True},
]


@pytest.fixture
def cfg(tmp_path: Path) -> ConfigManager:
    (tmp_path / "coinkeeper_configuration.json").write_text(json.dumps(CK), encoding="utf-8")
    c = ConfigManager(tmp_path / "config.json")
    c.data.update({"account_map": {"*1": "acc"}, "defaults": {"expense_cat_id": "gift", "income_cat_id": "inc"}})
    return c


def op(name="Теремок", cat=(11, "Кафе"), debit=True, oid="1"):
    return {
        "account": "*1", "parentCategory": {"id": cat[0], "name": cat[1]}, "operationName": name,
        "fullOperationName": name, "operationType": "Оплата", "debet": debit,
        "operationDate": "2026-06-28T11:08:01", "operationAmount": {"sum": 100.0},
        "operationId": oid, "properties": [],
    }


def conv(cfg, ops):
    return convert(ops, cfg, now=NOW)


def test_name_scope_rule_applies_to_similar_only(cfg):
    ops = [op("Теремок", oid="1"), op("Теремок", oid="2"), op("Bushe", oid="3")]
    plan = plan_rule(ops[0], "food", cfg, SCOPE_NAME)
    assert (plan.scope, plan.key, plan.rule) == (SCOPE_NAME, "Теремок", {"type": "expense", "cat_id": "food"})
    apply_plan(cfg, plan)
    dests = [t["destinationId"] for t in conv(cfg, ops).transactions]
    assert dests == ["food", "food", "gift"]  # Bushe — по умолчанию
    assert json.loads(cfg.config_path.read_text(encoding="utf-8"))["operation_name_rules"]["Теремок"]


def test_category_scope_rule_applies_to_whole_bank_category(cfg):
    ops = [op("Теремок", oid="1"), op("Bushe", oid="2"), op("Другое", cat=(94, "Переводы"), oid="3")]
    apply_plan(cfg, plan_rule(ops[0], "food", cfg, SCOPE_CATEGORY))
    assert cfg.data["vtb_category_rules"] == {"11": {"type": "expense", "cat_id": "food"}}
    assert [t["destinationId"] for t in conv(cfg, ops).transactions] == ["food", "food", "gift"]


def test_count_similar(cfg):
    rows = conv(cfg, [op("Теремок", oid="1"), op("Теремок", oid="2"), op("Bushe", oid="3"),
                      op("Теремок", debit=False, cat=(106, "Вх"), oid="4")]).rows
    base = rows[0].raw
    assert count_similar(rows, base, SCOPE_NAME) == 2       # входящая операция с тем же названием не считается
    assert count_similar(rows, base, SCOPE_CATEGORY) == 3   # вся категория банка 11


def test_category_scope_falls_back_to_name_without_bank_category(cfg):
    o = op("Без категории")
    o["parentCategory"] = None
    plan = plan_rule(o, "food", cfg, SCOPE_CATEGORY)
    assert plan.scope == SCOPE_NAME and plan.fell_back_to_name


def test_incoming_gets_prefixed_key_and_does_not_touch_outgoing_rule(cfg):
    out, inc = op("Иван", oid="1"), op("Иван", debit=False, cat=(106, "Вх"), oid="2")
    apply_plan(cfg, plan_rule(out, "gift", cfg, SCOPE_NAME))
    apply_plan(cfg, plan_rule(inc, "inc", cfg, SCOPE_NAME))
    assert set(cfg.data["operation_name_rules"]) == {"Иван", "доход:Иван"}
    tx = conv(cfg, [out, inc]).transactions
    assert [(t["sourceId"], t["destinationId"]) for t in tx] == [("acc", "gift"), ("inc", "acc")]


def test_goal_becomes_saving_and_debt_becomes_expense_with_type_5(cfg):
    assert plan_rule(op(), "goal", cfg, SCOPE_NAME).rule["type"] == "saving"
    plan = plan_rule(op(), "debt", cfg, SCOPE_NAME)
    apply_plan(cfg, plan)
    tx = conv(cfg, [op()]).transactions[0]
    assert (tx["destinationId"], tx["destinationType"]) == ("debt", 5)


@pytest.mark.parametrize("node, debit", [("inc", True), ("food", False), ("gone", True), ("ghost", True)])
def test_invalid_choices_are_rejected(cfg, node, debit):
    with pytest.raises(RuleError):
        plan_rule(op(debit=debit), node, cfg, SCOPE_NAME)


def test_changing_category_replaces_same_key_and_reports_previous(cfg):
    o = op()
    apply_plan(cfg, plan_rule(o, "food", cfg, SCOPE_NAME))
    plan = plan_rule(o, "gift", cfg, SCOPE_NAME)
    assert plan.replaces == {"type": "expense", "cat_id": "food"}
    apply_plan(cfg, plan)
    assert cfg.data["operation_name_rules"] == {"Теремок": {"type": "expense", "cat_id": "gift"}}
