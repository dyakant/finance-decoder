"""Конвертер банковских операций (выгрузка ВТБ) -> транзакции CoinKeeper.

Чистая логика без зависимостей от Qt: принимает список операций и конфиг,
возвращает ConversionResult со всеми данными, нужными UI (статистика,
неизвестные счета, операции без правил, строки предпросмотра).
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config_manager import (
    CK_ACCOUNT, CK_EXPENSE, CK_INCOME, CK_SAVING, ConfigManager,
)

CK_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)
VTB_INTERNAL_TRANSFER_CAT = 101

# Причины выбора правила
REASON_SKIP_DUP = "skip_dup"
REASON_OWN_TRANSFER = "auto_own_transfer"
REASON_FALLBACK = "fallback"


@dataclass
class PreviewRow:
    """Строка для таблицы предпросмотра в UI."""
    date: str
    bank_account: str
    name: str
    amount: float
    kind: str            # transfer / expense / income / saving
    source: str          # откуда (название узла CK)
    destination: str     # куда (название узла CK)
    reason: str
    needs_attention: bool


@dataclass
class Stats:
    total: int = 0
    converted: int = 0
    skipped_dups: int = 0
    skipped_rules: int = 0

    @property
    def gap(self) -> int:
        return self.total - (self.converted + self.skipped_dups + self.skipped_rules)


@dataclass
class FallbackGroup:
    """Группа операций одной категории банка, попавших в категорию по умолчанию."""
    bank_cat_id: str
    bank_cat_name: str
    direction: str                   # "expense" | "income" | "mixed"
    count: int
    example_names: list[str]
    example_ids: list[str]


@dataclass
class UnmatchedTransferGroup:
    """Переводы между своими счетами, у которых не найден счёт-получатель."""
    source_account: str
    receiver_account: str
    count: int
    example_name: str
    example_ids: list[str]


@dataclass
class ConversionResult:
    transactions: list[dict[str, Any]] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)
    rows: list[PreviewRow] = field(default_factory=list)
    unknown_accounts: list[str] = field(default_factory=list)
    unmatched_transfers: list[UnmatchedTransferGroup] = field(default_factory=list)
    fallback_groups: list[FallbackGroup] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Вспомогательные функции ──────────────────────────────────────────────────

def to_ticks(iso_str: str) -> int:
    """ISO 8601 -> .NET ticks (100 нс с 0001-01-01 UTC), без потери точности."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - CK_EPOCH) // timedelta(microseconds=1) * 10


def get_prop(properties: list[dict[str, Any]], key: str) -> Any:
    for p in properties:
        if p.get("key") == key:
            return p.get("value")
    return None


def _is_internal_transfer(op: dict[str, Any]) -> bool:
    cat_id = (op.get("parentCategory") or {}).get("id")
    op_type = (op.get("operationType") or "").lower()
    return cat_id == VTB_INTERNAL_TRANSFER_CAT or "своими счетами" in op_type


# ── Выбор правила ────────────────────────────────────────────────────────────

def _receiver_account(op: dict[str, Any], counterparts: dict[str, str]) -> str | None:
    """Счёт-получатель внутреннего перевода.

    Сначала свойство receiverAccount; если его нет — кредитная сторона того же
    перевода (общий chainId): её `account` и есть получатель.
    """
    return get_prop(op.get("properties", []), "receiverAccount") or counterparts.get(op.get("chainId", ""))


def _credit_counterparts(ops: list[dict[str, Any]]) -> dict[str, str]:
    """chainId -> счёт банка для кредитных сторон внутренних переводов."""
    return {
        op["chainId"]: op["account"]
        for op in ops
        if op.get("chainId") and op.get("account") and _is_internal_transfer(op) and not op.get("debet", True)
    }


def get_rule(
    op: dict[str, Any], cfg: ConfigManager, counterparts: dict[str, str] | None = None
) -> tuple[dict[str, Any] | None, str]:
    """Возвращает (правило, тег-причина)."""
    counterparts = counterparts or {}
    d = cfg.data
    cat = op.get("parentCategory") or {}
    vtb_cat_id = cat.get("id")
    op_type = op.get("operationType") or ""
    op_name = op.get("operationName") or ""
    full_name = op.get("fullOperationName") or ""
    is_debit = op.get("debet", True)

    # 1. Внутренние переводы: обе стороны есть в выгрузке — берём только дебетовую
    if _is_internal_transfer(op):
        if not is_debit:
            return None, REASON_SKIP_DUP
        receiver = _receiver_account(op, counterparts)
        src = d["account_map"].get(op.get("account", ""))
        dst = d["account_map"].get(receiver) if receiver else None
        if src and dst:
            return {"type": "transfer", "src_id": src, "dst_id": dst}, REASON_OWN_TRANSFER
        # второй счёт не найден — падаем в общие правила

    # 2. По parentCategory.id банка (ключи в JSON строковые)
    key = str(vtb_cat_id) if vtb_cat_id is not None else ""
    if key in d["vtb_category_rules"]:
        return d["vtb_category_rules"][key], f"vtb_cat:{vtb_cat_id}"

    # 3. По вхождению строки
    haystack = f"{op_type} {op_name} {full_name}".lower()
    for pattern, rule in d["operation_name_rules"].items():
        if pattern.lower() in haystack:
            return rule, f"name_match:{pattern}"

    # 4. Fallback
    if not is_debit:
        return {"type": "income", "cat_id": d["defaults"].get("income_cat_id", "")}, REASON_FALLBACK
    return {"type": "expense", "cat_id": d["defaults"].get("expense_cat_id", "")}, REASON_FALLBACK


# ── Сборка транзакции ────────────────────────────────────────────────────────

def build_tx(
    op: dict[str, Any],
    rule: dict[str, Any],
    cfg: ConfigManager,
    *,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    now: datetime | None = None,
) -> dict[str, Any]:
    account_map = cfg.data["account_map"]
    categories = cfg.data["categories"]

    amount = op["operationAmount"]["sum"]
    date_raw = op.get("operationDate") or op.get("transactionDate") or ""
    date_iso = date_raw.rstrip("Z").split(".")[0] + ".000Z" if date_raw else ""
    ticks = to_ticks(date_raw) if date_raw else 0
    now_ticks = to_ticks((now or datetime.now(timezone.utc)).isoformat())
    comment = (op.get("fullOperationName") or op.get("operationName") or "")
    comment += f" [{op.get('operationId', '')}]"

    account_id = account_map.get(op.get("account", ""), "")
    rt = rule["type"]

    if rt == "transfer":
        src_id, dst_id = rule["src_id"], rule["dst_id"]
        src_type = categories.get(src_id, {}).get("type", CK_ACCOUNT)
        dst_type = categories.get(dst_id, {}).get("type", CK_ACCOUNT)
    elif rt == "saving":
        src_id, src_type = account_id, CK_ACCOUNT
        dst_id, dst_type = rule["cat_id"], CK_SAVING
    elif rt == "income":
        src_id = rule["cat_id"]
        src_type = categories.get(src_id, {}).get("type", CK_INCOME)
        dst_id, dst_type = account_id, CK_ACCOUNT
    else:  # expense
        src_id, src_type = account_id, CK_ACCOUNT
        dst_id = rule["cat_id"]
        dst_type = categories.get(dst_id, {}).get("type", CK_EXPENSE)

    return {
        "id": new_id(),
        "tags": [],
        "sourceId": src_id,
        "sourceType": src_type,
        "sourceAmount": amount,
        "sourceName": None,
        "sourceCurrencyId": None,
        "destinationId": dst_id,
        "destinationType": dst_type,
        "destinationAmount": amount,
        "destinationName": None,
        "destinationCurrencyId": None,
        "defaultAmount": amount,
        "comment": comment,
        "deleted": False,
        "dateTimestamp": ticks,
        "dateTimestampISO": date_iso,
        "createdTimestamp": now_ticks,
        "timestamp": now_ticks,
        "debtPaymentAmount": 0,
        "isComplete": True,
        "counter": 0,
        "repeatingParentId": None,
        "importedTransactionId": op.get("operationId"),
    }


# ── Группировка проблемных операций ──────────────────────────────────────────

def _group_fallbacks(ops: list[dict[str, Any]]) -> list[FallbackGroup]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for op in ops:
        cat = op.get("parentCategory") or {}
        groups.setdefault((str(cat.get("id", "?")), cat.get("name", "")), []).append(op)

    result = []
    for (cat_id, cat_name), group in groups.items():
        debits = {bool(op.get("debet", True)) for op in group}
        direction = "expense" if debits == {True} else "income" if debits == {False} else "mixed"
        names = sorted({op.get("operationName", "") for op in group})
        result.append(FallbackGroup(
            bank_cat_id=cat_id,
            bank_cat_name=cat_name,
            direction=direction,
            count=len(group),
            example_names=names[:4],
            example_ids=[str(op.get("operationId", "")) for op in group[:3]],
        ))
    return sorted(result, key=lambda g: -g.count)


def _group_unmatched(
    ops: list[dict[str, Any]], counterparts: dict[str, str]
) -> list[UnmatchedTransferGroup]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for op in ops:
        receiver = _receiver_account(op, counterparts) or "неизвестен"
        groups.setdefault((op.get("account", "?"), receiver), []).append(op)
    return sorted(
        (
            UnmatchedTransferGroup(
                source_account=src,
                receiver_account=dst,
                count=len(g),
                example_name=g[0].get("operationName", ""),
                example_ids=[str(op.get("operationId", "")) for op in g[:3]],
            )
            for (src, dst), g in groups.items()
        ),
        key=lambda g: -g.count,
    )


# ── Основная функция ─────────────────────────────────────────────────────────

def convert(
    ops: list[dict[str, Any]],
    cfg: ConfigManager,
    *,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    now: datetime | None = None,
) -> ConversionResult:
    res = ConversionResult()
    res.stats.total = len(ops)

    # Счета банка, встретившиеся в выгрузке, но не прописанные в account_map
    seen_accounts = {op.get("account") for op in ops if op.get("account")}
    res.unknown_accounts = sorted(a for a in seen_accounts if not cfg.is_known_account(a))

    fallback_ops: list[dict[str, Any]] = []
    unmatched_ops: list[dict[str, Any]] = []
    counterparts = _credit_counterparts(ops)

    for i, op in enumerate(ops):
        try:
            rule, reason = get_rule(op, cfg, counterparts)
            if reason == REASON_SKIP_DUP:
                res.stats.skipped_dups += 1
                continue
            if rule is None or rule.get("type") == "skip":
                res.stats.skipped_rules += 1
                continue

            attention = False
            if reason == REASON_FALLBACK:
                fallback_ops.append(op)
                attention = True
                if _is_internal_transfer(op) and op.get("debet", True):
                    unmatched_ops.append(op)

            tx = build_tx(op, rule, cfg, new_id=new_id, now=now)
        except (KeyError, TypeError, ValueError) as e:
            res.errors.append(f"Операция #{i} ({op.get('operationId', '?')}): {type(e).__name__}: {e}")
            continue

        res.transactions.append(tx)
        res.stats.converted += 1
        res.rows.append(PreviewRow(
            date=tx["dateTimestampISO"][:10],
            bank_account=op.get("account", ""),
            name=op.get("operationName") or op.get("fullOperationName") or "",
            amount=tx["sourceAmount"],
            kind=rule["type"],
            source=cfg.ck_name(tx["sourceId"]) if tx["sourceId"] else "⚠ не задан",
            destination=cfg.ck_name(tx["destinationId"]) if tx["destinationId"] else "⚠ не задан",
            reason=reason,
            needs_attention=attention,
        ))

    res.fallback_groups = _group_fallbacks(
        [op for op in fallback_ops if not any(op is u for u in unmatched_ops)]
    )
    res.unmatched_transfers = _group_unmatched(unmatched_ops, counterparts)
    return res
