import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config_manager import ConfigManager


@dataclass
class TransformResult:
    output_data: dict[str, Any] = field(default_factory=dict)
    unknown_accounts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_input(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def transform(input_data: dict[str, Any], config: ConfigManager) -> TransformResult:
    """
    Пример трансформации. Ожидаемый вход:
        {"transactions": [{"account": "ACC1", "amount": 100, "category": "Еда"}, ...]}
    Выход:
        {"transactions": [{"account_name": ..., "category": ..., "amount": ...}, ...]}
    """
    result = TransformResult()
    raw_txs = input_data.get("transactions", [])
    if not isinstance(raw_txs, list):
        result.errors.append("Поле 'transactions' отсутствует или не является списком")
        return result

    unknown = set()
    out_txs = []

    known_categories = set(config.get_categories())

    for i, tx in enumerate(raw_txs):
        account = tx.get("account")
        if not account:
            result.errors.append(f"Транзакция #{i}: отсутствует поле 'account'")
            continue

        if not config.is_known_account(account):
            unknown.add(account)

        category = tx.get("category", "")
        if category and category not in known_categories:
            result.errors.append(f"Транзакция #{i}: неизвестная категория '{category}'")

        out_txs.append({
            "account_id": account,
            "account_name": config.data["accounts"].get(account, "<UNKNOWN>"),
            "category": category,
            "amount": tx.get("amount", 0),
        })

    result.output_data = {"transactions": out_txs}
    result.unknown_accounts = sorted(unknown)
    return result


def run_transform(input_path: Path, output_path: Path, config: ConfigManager) -> TransformResult:
    data = load_input(input_path)
    result = transform(data, config)
    if not result.unknown_accounts:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.output_data, f, ensure_ascii=False, indent=2)
    return result