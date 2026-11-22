import copy
import json
from pathlib import Path
from typing import Any

# Типы узлов CoinKeeper (sourceType / destinationType)
CK_INCOME = 1    # категория дохода
CK_ACCOUNT = 2   # счёт
CK_EXPENSE = 3   # категория расхода
CK_SAVING = 6    # цель накопления

CK_TYPE_NAMES = {
    CK_INCOME: "Доход",
    CK_ACCOUNT: "Счёт",
    CK_EXPENSE: "Расход",
    CK_SAVING: "Накопление",
}

RULE_TYPES = ("expense", "income", "saving", "transfer", "skip")

DEFAULT_CONFIG: dict[str, Any] = {
    # номер счёта в банке ("*0683") -> ID счёта в CoinKeeper
    "account_map": {},
    # ID в CoinKeeper -> {"name": str, "type": 1|2|3|6}
    "categories": {},
    # parentCategory.id банка (строкой) -> {"type": "expense", "cat_id": "..."}
    "vtb_category_rules": {},
    # подстрока в названии операции -> правило
    "operation_name_rules": {},
    "defaults": {"expense_cat_id": "", "income_cat_id": ""},
}


def _strip_comments(obj: Any) -> Any:
    """Удаляет служебные ключи _comment на всех уровнях."""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if k != "_comment"}
    if isinstance(obj, list):
        return [_strip_comments(i) for i in obj]
    return obj


class ConfigManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.data: dict[str, Any] = {}
        self.load_warnings: list[str] = []
        self.load()

    # --- Загрузка / сохранение ---
    def load(self) -> None:
        self.load_warnings = []
        raw: dict[str, Any] | None = None
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    raw = _strip_comments(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                self.load_warnings.append(
                    f"Ошибка чтения конфига: {e}. Используется конфиг по умолчанию."
                )

        self.data = copy.deepcopy(DEFAULT_CONFIG)
        if raw is not None:
            self._merge_raw(raw)
        elif not self.config_path.exists():
            self.save()

    def _merge_raw(self, raw: dict[str, Any]) -> None:
        # Старый формат (accounts / categories-списком) несовместим с новым
        if isinstance(raw.get("categories"), list) or "accounts" in raw:
            self.load_warnings.append(
                "Обнаружен конфиг старого формата (accounts / categories-список): "
                "он не содержит ID CoinKeeper и был проигнорирован. "
                "Заполните счета и категории заново в редакторе конфига."
            )
            raw = {k: v for k, v in raw.items() if k not in ("accounts", "categories")}
        for key, default in DEFAULT_CONFIG.items():
            value = raw.get(key)
            if isinstance(value, dict):
                if key == "defaults":
                    self.data[key] = {**default, **value}
                else:
                    self.data[key] = value

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def validate(self) -> list[str]:
        """Возвращает список проблем конфигурации (пусто — всё в порядке)."""
        problems: list[str] = []
        cats = self.data["categories"]
        for key in ("expense_cat_id", "income_cat_id"):
            cid = self.data["defaults"].get(key, "")
            if not cid:
                problems.append(f"defaults.{key} не задан — операции без правил некуда класть")
            elif cid not in cats:
                problems.append(f"defaults.{key}: категория {cid} не найдена в categories")
        for acc, ck_id in self.data["account_map"].items():
            if ck_id not in cats:
                problems.append(f"Счёт {acc}: ID {ck_id} отсутствует в categories")
        for source in ("vtb_category_rules", "operation_name_rules"):
            for pattern, rule in self.data[source].items():
                if rule.get("type") not in RULE_TYPES:
                    problems.append(f"{source}[{pattern}]: неизвестный тип правила {rule.get('type')!r}")
                elif rule["type"] in ("expense", "income", "saving") and rule.get("cat_id") not in cats:
                    problems.append(f"{source}[{pattern}]: cat_id {rule.get('cat_id')!r} не найден в categories")
        return problems

    # --- Счета (банковский счёт -> счёт CoinKeeper) ---
    def is_known_account(self, account: str) -> bool:
        return account in self.data["account_map"]

    def add_account(self, bank_account: str, ck_id: str) -> None:
        self.data["account_map"][bank_account] = ck_id
        self.save()

    def remove_account(self, bank_account: str) -> None:
        self.data["account_map"].pop(bank_account, None)
        self.save()

    # --- Узлы CoinKeeper: счета, категории, накопления ---
    def get_ck_nodes(self, types: tuple[int, ...] | None = None) -> dict[str, dict[str, Any]]:
        cats = self.data["categories"]
        if types is None:
            return dict(cats)
        return {cid: c for cid, c in cats.items() if c.get("type") in types}

    def ck_name(self, ck_id: str) -> str:
        node = self.data["categories"].get(ck_id)
        return node.get("name", ck_id) if node else ck_id

    def add_ck_node(self, ck_id: str, name: str, node_type: int) -> None:
        if ck_id:
            self.data["categories"][ck_id] = {"name": name, "type": node_type}
            self.save()

    def remove_ck_node(self, ck_id: str) -> None:
        self.data["categories"].pop(ck_id, None)
        self.save()

    # --- Правила ---
    def set_vtb_rule(self, vtb_cat_id: str, rule: dict[str, Any]) -> None:
        self.data["vtb_category_rules"][str(vtb_cat_id)] = rule
        self.save()

    def remove_vtb_rule(self, vtb_cat_id: str) -> None:
        self.data["vtb_category_rules"].pop(str(vtb_cat_id), None)
        self.save()

    def set_name_rule(self, pattern: str, rule: dict[str, Any]) -> None:
        self.data["operation_name_rules"][pattern] = rule
        self.save()

    def remove_name_rule(self, pattern: str) -> None:
        self.data["operation_name_rules"].pop(pattern, None)
        self.save()

    def set_defaults(self, expense_cat_id: str, income_cat_id: str) -> None:
        self.data["defaults"] = {
            "expense_cat_id": expense_cat_id,
            "income_cat_id": income_cat_id,
        }
        self.save()
