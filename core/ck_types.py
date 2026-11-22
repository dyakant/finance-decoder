"""Типы узлов CoinKeeper (поле categoryType в конфигурации, sourceType/destinationType в транзакциях)."""

CK_INCOME = 1    # доход — поступление денежных средств
CK_ACCOUNT = 2   # счёт / кошелёк — место хранения денег
CK_EXPENSE = 3   # расход — траты
CK_DEBT = 5      # кредит / долг — обязательства по заёмным средствам
CK_SAVING = 6    # цель / накопление — финансовые цели и резервы

CK_TYPE_NAMES = {
    CK_INCOME: "Доход",
    CK_ACCOUNT: "Счёт",
    CK_EXPENSE: "Расход",
    CK_DEBT: "Кредит / долг",
    CK_SAVING: "Цель / накопление",
}

# Порядок показа типов в UI
CK_TYPE_ORDER = (CK_ACCOUNT, CK_INCOME, CK_EXPENSE, CK_SAVING, CK_DEBT)
