import json
from pathlib import Path

import pytest

from core.coinkeeper_config import CoinKeeperFormatError, CoinKeeperStore, parse_text
from core.config_manager import CK_DEBT, ConfigManager
from core.converter import convert


def cat(id_, name, type_, deleted=False, **kw):
    return {
        "id": id_, "name": name, "currencyId": "RUB", "categoryType": type_,
        "deleted": deleted, "deletedWithTransactions": deleted, "order": 1,
        "icon": "Card", "amount": 0.0, "limitAmount": 0.0, **kw,
    }


SAMPLE = [
    cat("acc1", "ВТБ", 2),
    cat("acc_old", "Старый счёт", 2, deleted=True),
    cat("inc1", "Зарплата", 1),
    cat("exp1", "Питание", 3),
    cat("debt1", "Кредит", 5),
    cat("goal1", "Подушка", 6),
]


def bracketless(objs, sep=",\r\n"):
    """Формат выгрузки CoinKeeper: объекты через запятую без внешних скобок."""
    return sep.join(json.dumps(o, ensure_ascii=False, indent=4) for o in objs)


def test_parse_objects_without_outer_brackets():
    raws, warnings = parse_text(bracketless(SAMPLE))
    assert [r["id"] for r in raws] == [c["id"] for c in SAMPLE] and not warnings


def test_parse_array_bom_trailing_comma_and_wrapper():
    assert len(parse_text("﻿" + json.dumps(SAMPLE))[0]) == 6
    assert len(parse_text(bracketless(SAMPLE) + ",\n")[0]) == 6
    assert len(parse_text(json.dumps({"categories": SAMPLE}))[0]) == 6


def test_parse_skips_bad_objects_and_duplicates():
    raws, warnings = parse_text(json.dumps([cat("a", "A", 2), {"name": "no id"}, cat("a", "A2", 2)]))
    assert len(raws) == 1 and raws[0]["name"] == "A2" and len(warnings) == 2


@pytest.mark.parametrize("text", ["", "   ", "not json", "[]", '[{"x": 1}]'])
def test_parse_rejects_garbage(text):
    with pytest.raises(CoinKeeperFormatError):
        parse_text(text)


def test_store_import_normalizes_and_reports_diff(tmp_path: Path):
    src = tmp_path / "src.json"
    src.write_text(bracketless(SAMPLE), encoding="utf-8")
    store = CoinKeeperStore(tmp_path / "cfg" / "coinkeeper_configuration.json")
    assert not store.exists and not store.categories

    s1 = store.import_file(src)
    assert (s1.total, s1.added, s1.removed, s1.changed) == (6, 6, 0, 0)
    # файл хранения — корректный JSON-массив со всеми полями
    stored = json.loads(store.path.read_text(encoding="utf-8"))
    assert isinstance(stored, list) and stored[0]["icon"] == "Card"
    assert store.counts()[2] == (1, 1)  # счета: 1 активный, 1 удалённый

    changed = [dict(SAMPLE[0], name="ВТБ новый")] + SAMPLE[2:] + [cat("new", "Новая", 3)]
    src.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    assert store.diff_with(src).added == 1  # diff не пишет в файл
    assert len(store.categories) == 6
    s2 = store.import_file(src)
    assert (s2.added, s2.removed, s2.changed) == (1, 1, 1)
    assert store.get("acc1").name == "ВТБ новый"
    assert store.path.with_name(store.path.name + ".bak").exists()


def test_store_broken_file_gives_warning_not_crash(tmp_path: Path):
    p = tmp_path / "coinkeeper_configuration.json"
    p.write_text("{{{", encoding="utf-8")
    store = CoinKeeperStore(p)
    assert not store.categories and store.warnings


@pytest.fixture
def cfg(tmp_path: Path) -> ConfigManager:
    (tmp_path / "coinkeeper_configuration.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    c = ConfigManager(tmp_path / "config.json")
    c.data.update({
        "account_map": {"*1": "acc1", "*2": "acc_old"},
        "defaults": {"expense_cat_id": "exp1", "income_cat_id": "inc1"},
    })
    return c


def test_config_uses_coinkeeper_nodes_and_hides_deleted(cfg):
    assert set(cfg.get_ck_nodes((2,))) == {"acc1"}
    assert set(cfg.get_ck_nodes((2,), include_deleted=True)) == {"acc1", "acc_old"}
    assert cfg.ck_name("acc_old") == "Старый счёт (удалён)"
    assert cfg.nodes()["debt1"]["type"] == CK_DEBT


def test_legacy_categories_are_fallback_only(cfg):
    cfg.data["categories"] = {"legacy": {"name": "Ручной", "type": 3}, "acc1": {"name": "перекрыто", "type": 3}}
    assert cfg.nodes()["legacy"]["name"] == "Ручной"
    assert cfg.nodes()["acc1"]["name"] == "ВТБ"  # конфигурация CoinKeeper приоритетнее


def test_validate_flags_deleted_and_missing(cfg):
    cfg.data["vtb_category_rules"] = {"7": {"type": "expense", "cat_id": "ghost"}}
    problems = "\n".join(cfg.validate())
    assert "Старый счёт" in problems and "удалён" in problems  # счёт *2 удалён
    assert "ghost" in problems
    assert "не загружена" not in problems


def test_validate_flags_missing_store(tmp_path):
    assert any("не загружена" in p for p in ConfigManager(tmp_path / "config.json").validate())


def test_payment_to_debt_node_gets_type_5(cfg):
    cfg.data["vtb_category_rules"] = {"50": {"type": "expense", "cat_id": "debt1"}}
    op = {
        "account": "*1", "parentCategory": {"id": 50, "name": "Платёж по кредиту"}, "debet": True,
        "operationDate": "2026-06-28T11:08:01.905", "operationAmount": {"sum": 500.0},
        "operationId": "1", "operationName": "Кредит", "properties": [],
    }
    tx = convert([op], cfg).transactions[0]
    assert (tx["sourceId"], tx["sourceType"]) == ("acc1", 2)
    assert (tx["destinationId"], tx["destinationType"]) == ("debt1", 5)
