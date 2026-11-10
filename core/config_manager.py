import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "accounts": {},      # {"ACC123": "Зарплатный счёт", ...}
    "categories": [],    # ["Еда", "Транспорт", ...]
    "rules": {}          # зарезервировано для будущих правил маппинга
}


class ConfigManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"[ConfigManager] Ошибка чтения конфига: {e}. Используется конфиг по умолчанию.")
                self.data = DEFAULT_CONFIG.copy()
        else:
            self.data = DEFAULT_CONFIG.copy()
            self.save()

        # Гарантируем наличие всех ключей
        for key, value in DEFAULT_CONFIG.items():
            self.data.setdefault(key, value if not isinstance(value, dict) else {})

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # --- Счета ---
    def is_known_account(self, account: str) -> bool:
        return account in self.data.get("accounts", {})

    def add_account(self, account: str, display_name: str = "") -> None:
        self.data.setdefault("accounts", {})[account] = display_name or account
        self.save()

    def remove_account(self, account: str) -> None:
        self.data.get("accounts", {}).pop(account, None)
        self.save()

    # --- Категории ---
    def get_categories(self) -> list[str]:
        return list(self.data.get("categories", []))

    def add_category(self, name: str) -> None:
        cats = self.data.setdefault("categories", [])
        if name and name not in cats:
            cats.append(name)
            self.save()

    def remove_category(self, name: str) -> None:
        cats = self.data.get("categories", [])
        if name in cats:
            cats.remove(name)
            self.save()