from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.config_manager import ConfigManager
from core.converter import convert, to_ticks

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def cfg(tmp_path: Path) -> ConfigManager:
    c = ConfigManager(tmp_path / "config.json")
    c.data.update({
        "account_map": {"*0683": "acc_main", "*0912": "acc_save"},
        "categories": {
            "acc_main": {"name": "Основной", "type": 2},
            "acc_save": {"name": "Накопительный", "type": 2},
            "cat_food": {"name": "Еда", "type": 3},
            "cat_misc": {"name": "Разное", "type": 3},
            "cat_in": {"name": "Прочие доходы", "type": 1},
            "cat_salary": {"name": "Зарплата", "type": 1},
        },
        "vtb_category_rules": {"11": {"type": "expense", "cat_id": "cat_food"}},
        "operation_name_rules": {"заработной платы": {"type": "income", "cat_id": "cat_salary"}},
        "defaults": {"expense_cat_id": "cat_misc", "income_cat_id": "cat_in"},
    })
    return c


def op(**kw):
    base = {
        "account": "*0683",
        "parentCategory": {"id": 11, "name": "Супермаркеты"},
        "operationName": "Магазин",
        "fullOperationName": "Магазин",
        "operationType": "Оплата товаров и услуг",
        "debet": True,
        "operationDate": "2026-06-28T11:08:01.905",
        "operationAmount": {"currency": "RUB", "sum": 100.0},
        "operationId": "1",
        "properties": [],
    }
    base.update(kw)
    return base


def run(ops, cfg):
    counter = iter(range(1000))
    return convert(ops, cfg, new_id=lambda: f"id{next(counter)}", now=NOW)


def test_expense_by_vtb_category(cfg):
    r = run([op()], cfg)
    tx = r.transactions[0]
    assert (tx["sourceId"], tx["destinationId"]) == ("acc_main", "cat_food")
    assert tx["destinationType"] == 3 and tx["sourceType"] == 2
    assert tx["importedTransactionId"] == "1"
    assert r.stats.gap == 0 and not r.fallback_groups


def test_name_rule_income(cfg):
    r = run([op(parentCategory={"id": 90, "name": "ЗП"}, debet=False,
               operationName="Поступление заработной платы")], cfg)
    tx = r.transactions[0]
    assert (tx["sourceId"], tx["destinationId"]) == ("cat_salary", "acc_main")


def test_own_transfer_dedup_and_match(cfg):
    debit = op(parentCategory={"id": 101, "name": "Между счетами"}, operationType="Между своими счетами",
               properties=[{"key": "receiverAccount", "value": "*0912"}], operationId="a")
    credit = op(parentCategory={"id": 101, "name": "Между счетами"}, operationType="Между своими счетами",
                debet=False, account="*0912", operationId="b")
    r = run([debit, credit], cfg)
    assert r.stats.skipped_dups == 1 and r.stats.converted == 1
    tx = r.transactions[0]
    assert (tx["sourceId"], tx["destinationId"]) == ("acc_main", "acc_save")
    assert r.stats.gap == 0


def test_own_transfer_receiver_from_credit_side_chain_id(cfg):
    kw = dict(parentCategory={"id": 101, "name": "Между счетами"}, operationType="Между своими счетами")
    debit = op(chainId="c1", operationId="a", **kw)          # receiverAccount отсутствует
    credit = op(chainId="c1", operationId="b", debet=False, account="*0912", **kw)
    r = run([debit, credit], cfg)
    tx = r.transactions[0]
    assert (tx["sourceId"], tx["destinationId"]) == ("acc_main", "acc_save")
    assert not r.unmatched_transfers


def test_unmatched_transfer_goes_to_fallback_and_is_reported_once(cfg):
    o = op(parentCategory={"id": 101, "name": "Между счетами"}, operationType="Между своими счетами",
           properties=[{"key": "receiverAccount", "value": "*9999"}])
    r = run([o], cfg)
    assert r.transactions[0]["destinationId"] == "cat_misc"
    assert len(r.unmatched_transfers) == 1 and r.unmatched_transfers[0].receiver_account == "*9999"
    assert r.fallback_groups == []  # не дублируем в общем списке


def test_fallback_groups(cfg):
    ops = [op(parentCategory={"id": 77, "name": "Новая"}, operationId=str(i)) for i in range(3)]
    r = run(ops, cfg)
    assert len(r.fallback_groups) == 1
    g = r.fallback_groups[0]
    assert (g.bank_cat_id, g.count, g.direction) == ("77", 3, "expense")
    assert all(row.needs_attention for row in r.rows)


def test_unknown_account_detected(cfg):
    r = run([op(account="*5555")], cfg)
    assert r.unknown_accounts == ["*5555"]


def test_skip_rule(cfg):
    cfg.data["vtb_category_rules"]["12"] = {"type": "skip"}
    r = run([op(parentCategory={"id": 12, "name": "x"})], cfg)
    assert r.stats.skipped_rules == 1 and not r.transactions


def test_ticks_exact():
    assert to_ticks("0001-01-01T00:00:00Z") == 0
    assert to_ticks("0001-01-01T00:00:01.5") == 15_000_000


def test_bad_operation_reported_not_fatal(cfg):
    bad = op()
    del bad["operationAmount"]
    r = run([bad, op(operationId="2")], cfg)
    assert len(r.errors) == 1 and r.stats.converted == 1
    assert r.stats.gap == 1  # битая операция видна в разнице


def test_validate_flags_missing_defaults(tmp_path):
    c = ConfigManager(tmp_path / "c.json")
    assert any("defaults.expense_cat_id" in p for p in c.validate())


def test_preview_row_keeps_raw_operation(cfg):
    o = op(operationId="42")
    r = run([o], cfg)
    assert r.rows[0].raw is o
