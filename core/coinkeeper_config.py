"""Конфигурация CoinKeeper: счета, категории доходов/расходов, цели и долги.

Исходный файл (выгрузка из CoinKeeper) — набор JSON-объектов, который может быть
записан без внешних скобок `[ ]`, через запятую. Загрузчик понимает такой формат,
обычный JSON-массив и объект вида {"categories": [...]}.

Внутри приложения конфигурация хранится в файле хранения (по умолчанию
config/coinkeeper_configuration.json) уже в виде корректного JSON-массива,
со всеми полями исходных объектов.
"""
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .ck_types import CK_TYPE_ORDER

STORAGE_FILENAME = "coinkeeper_configuration.json"


class CoinKeeperFormatError(ValueError):
    """Файл не похож на конфигурацию CoinKeeper."""


@dataclass(frozen=True)
class CKCategory:
    id: str
    name: str
    category_type: int
    currency: str
    deleted: bool
    deleted_with_transactions: bool
    icon: str
    order: int
    parent_uid: str
    amount: float
    limit_amount: float
    except_from_balance: bool
    raw: dict[str, Any] = field(compare=False, repr=False)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "CKCategory":
        return cls(
            id=str(raw["id"]),
            name=str(raw.get("name", "")),
            category_type=int(raw["categoryType"]),
            currency=str(raw.get("currencyId") or ""),
            deleted=bool(raw.get("deleted", False)),
            deleted_with_transactions=bool(raw.get("deletedWithTransactions", False)),
            icon=str(raw.get("icon") or ""),
            order=int(raw.get("order") or 0),
            parent_uid=str(raw.get("parentUid") or ""),
            amount=float(raw.get("amount") or 0.0),
            limit_amount=float(raw.get("limitAmount") or 0.0),
            except_from_balance=bool(raw.get("exceptFromBalance", False)),
            raw=raw,
        )

    @property
    def status(self) -> str:
        if not self.deleted:
            return "активна"
        return "удалена (с транзакциями)" if self.deleted_with_transactions else "удалена"


@dataclass
class ImportSummary:
    total: int = 0
    added: int = 0
    removed: int = 0
    changed: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_text(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Разбирает текст выгрузки. Возвращает (объекты, предупреждения)."""
    text = text.lstrip("﻿").strip()
    if not text:
        raise CoinKeeperFormatError("Файл пустой")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Формат выгрузки: объекты через запятую без внешних скобок
        try:
            data = json.loads("[" + text.rstrip(",").rstrip() + "]")
        except json.JSONDecodeError as e:
            raise CoinKeeperFormatError(f"Не удалось разобрать JSON: {e}") from e

    if isinstance(data, dict):
        inner = data.get("categories")
        data = inner if isinstance(inner, list) else [data]
    if not isinstance(data, list):
        raise CoinKeeperFormatError("Ожидался список объектов конфигурации")

    warnings: list[str] = []
    result: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "id" not in item or "categoryType" not in item:
            warnings.append(f"Объект #{i}: нет полей id / categoryType — пропущен")
            continue
        try:
            CKCategory.from_raw(item)
        except (TypeError, ValueError) as e:
            warnings.append(f"Объект #{i} ({item.get('name', '?')}): {e} — пропущен")
            continue
        if str(item["id"]) in result:
            warnings.append(f"Повторяющийся id {item['id']} ({item.get('name', '?')}) — взят последний")
        result[str(item["id"])] = item

    if not result:
        raise CoinKeeperFormatError("В файле не найдено ни одного объекта с id и categoryType")
    return list(result.values()), warnings


def _sort_key(c: CKCategory) -> tuple:
    t = c.category_type
    return (CK_TYPE_ORDER.index(t) if t in CK_TYPE_ORDER else len(CK_TYPE_ORDER), c.deleted, c.order, c.name.lower())


class CoinKeeperStore:
    """Файл хранения конфигурации CoinKeeper + загруженные из него объекты."""

    def __init__(self, path: Path):
        self.path = path
        self.categories: list[CKCategory] = []
        self.warnings: list[str] = []
        self._by_id: dict[str, CKCategory] = {}
        self._nodes: dict[str, dict[str, Any]] = {}
        self.load()

    # --- Чтение ---
    def load(self) -> None:
        self.categories, self.warnings = [], []
        if self.path.exists():
            try:
                raws, self.warnings = parse_text(self.path.read_text(encoding="utf-8"))
                self.categories = sorted((CKCategory.from_raw(r) for r in raws), key=_sort_key)
            except (CoinKeeperFormatError, OSError) as e:
                self.warnings.append(f"Файл хранения {self.path.name}: {e}")
        self._by_id = {c.id: c for c in self.categories}
        self._nodes = {
            c.id: {"name": c.name.strip(), "type": c.category_type, "deleted": c.deleted, "currency": c.currency}
            for c in self.categories
        }

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def get(self, ck_id: str) -> CKCategory | None:
        return self._by_id.get(ck_id)

    def nodes(self) -> dict[str, dict[str, Any]]:
        """id -> {"name", "type", "deleted", "currency"} (включая удалённые)."""
        return self._nodes

    def counts(self) -> dict[int, tuple[int, int]]:
        """categoryType -> (активных, удалённых)."""
        res: dict[int, list[int]] = {}
        for c in self.categories:
            res.setdefault(c.category_type, [0, 0])[1 if c.deleted else 0] += 1
        return {t: (a, d) for t, (a, d) in res.items()}

    def file_info(self) -> tuple[int, datetime] | None:
        """(размер в байтах, время изменения) или None, если файла нет."""
        try:
            st = self.path.stat()
        except OSError:
            return None
        return st.st_size, datetime.fromtimestamp(st.st_mtime)

    # --- Импорт ---
    def diff_with(self, src: Path) -> ImportSummary:
        """Что изменится при загрузке файла src (без записи)."""
        raws, warnings = parse_text(Path(src).read_text(encoding="utf-8"))
        new = {str(r["id"]): r for r in raws}
        old = {c.id: c.raw for c in self.categories}
        return ImportSummary(
            total=len(new),
            added=len(new.keys() - old.keys()),
            removed=len(old.keys() - new.keys()),
            changed=sum(1 for k in new.keys() & old.keys() if new[k] != old[k]),
            warnings=warnings,
        )

    def import_file(self, src: Path) -> ImportSummary:
        """Заменяет содержимое файла хранения конфигурацией из src."""
        summary = self.diff_with(src)
        raws, _ = parse_text(Path(src).read_text(encoding="utf-8"))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raws, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

        self.load()
        return summary
