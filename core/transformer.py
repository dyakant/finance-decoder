import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config_manager import ConfigManager
from .converter import ConversionResult, convert


@dataclass
class TransformResult:
    conversion: ConversionResult = field(default_factory=ConversionResult)
    config_problems: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    written: bool = False

    @property
    def unknown_accounts(self) -> list[str]:
        return self.conversion.unknown_accounts


def load_input(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def transform(input_data: dict[str, Any], config: ConfigManager) -> TransformResult:
    """Выгрузка банка {"operations": [...]} -> список транзакций CoinKeeper."""
    result = TransformResult(config_problems=config.validate())
    ops = input_data.get("operations")
    if not isinstance(ops, list) or not ops:
        result.errors.append("Ключ 'operations' отсутствует, пуст или не является списком")
        return result

    result.conversion = convert(ops, config)
    result.errors.extend(result.conversion.errors)
    return result


def run_transform(input_path: Path, output_path: Path, config: ConfigManager) -> TransformResult:
    result = transform(load_input(input_path), config)
    # Пока есть неизвестные счета, ID счёта в транзакциях был бы пустым — файл не пишем
    if result.conversion.transactions and not result.unknown_accounts:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.conversion.transactions, f, ensure_ascii=False, indent=2)
        result.written = True
    return result
