from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent / "server" / "prico-demo" / "frozen_snapshot"
JSON_ROOT = ROOT / "json"
SCHEMA_REPORT = Path("/Users/danielbenassaya/Code/personal/Prico/schema_report.md")

TABLES = [
    "prico.bankim",
    "prico.lekohot",
    "prico.matbeot",
    "prico.iskaot",
    "prico.nigrarot_bankaiyot",
    "prico.paku",
    "prico.ssars",
    "prico.yoman",
    "dbo.CurrencyPairsHistory",
    "dbo.CustomerTransactions",
    "dbo.DealsConfirmations",
    "dbo.DealChangesLogHeaders",
    "dbo.DealChangesLogLines",
]

PAIR_TO_IDS = {
    "USD/ILS": (1, 40),
    "EUR/ILS": (6, 40),
    "GBP/ILS": (5, 40),
}

PAIR_TO_CODES = {
    "USD/ILS": ("USD", "ILS"),
    "EUR/ILS": ("EUR", "ILS"),
    "GBP/ILS": ("GBP", "ILS"),
}

BANKS = [
    {"mispar_bank": 2, "bank": 2, "teur_bank": "Discount", "Teur_English": "Discount Bank", "fax": "", "mail": "fx@discount.local", "swipt": "DSCTILIT", "derug": "A", "BlumbergID": "DSCT"},
    {"mispar_bank": 11, "bank": 11, "teur_bank": "Leumi", "Teur_English": "Bank Leumi", "fax": "", "mail": "fx@leumi.local", "swipt": "LUMIILIT", "derug": "A", "BlumbergID": "LUMI"},
    {"mispar_bank": 26, "bank": 26, "teur_bank": "Hapoalim", "Teur_English": "Bank Hapoalim", "fax": "", "mail": "fx@hapoalim.local", "swipt": "POALILIT", "derug": "A", "BlumbergID": "POLI"},
    {"mispar_bank": 34, "bank": 34, "teur_bank": "Mizrahi", "Teur_English": "Mizrahi Tefahot", "fax": "", "mail": "fx@mizrahi.local", "swipt": "MIZBILIT", "derug": "A", "BlumbergID": "MZTF"},
]

CURRENCIES = [
    {"mispar_matbea": 1, "teur_matbea": "USD", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "USD", "Curr_Heb_Name": "US Dollar", "CurrSign": "$", "HashCurrencyID": "USD"},
    {"mispar_matbea": 5, "teur_matbea": "GBP", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "GBP", "Curr_Heb_Name": "Pound", "CurrSign": "GBP", "HashCurrencyID": "GBP"},
    {"mispar_matbea": 6, "teur_matbea": "EUR", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "EUR", "Curr_Heb_Name": "Euro", "CurrSign": "EUR", "HashCurrencyID": "EUR"},
    {"mispar_matbea": 40, "teur_matbea": "ILS", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "ILS", "Curr_Heb_Name": "Shekel", "CurrSign": "ILS", "HashCurrencyID": "ILS"},
]

CLIENTS = [
    {
        "id": 32001,
        "name": "Orion Foods",
        "english": "Orion Foods Ltd",
        "sector": "Food Imports",
        "base_currency": 1,
        "deal_count": 18,
        "pair_cycle": ["USD/ILS", "USD/ILS", "EUR/ILS", "USD/ILS", "GBP/ILS", "USD/ILS"],
        "bank_cycle": [26, 2, 11, 26, 34, 2],
        "product_cycle": [6, 4, 8, 18, 6, 4],
        "base_notional": 240_000,
        "account": "000320010001",
        "branch": 101,
        "project_prefix": "ORION",
        "tx_count": 20,
        "tx_currency_cycle": ["USD", "USD", "EUR", "USD", "GBP"],
        "tx_type_cycle": ["Inventory Purchase", "Raw Materials", "Freight Settlement", "Import Payment", "Commodity Hedge"],
    },
    {
        "id": 32002,
        "name": "Atlas Medical",
        "english": "Atlas Medical Systems",
        "sector": "MedTech",
        "base_currency": 6,
        "deal_count": 16,
        "pair_cycle": ["EUR/ILS", "EUR/ILS", "USD/ILS", "EUR/ILS", "USD/ILS", "GBP/ILS"],
        "bank_cycle": [11, 34, 2, 11, 26, 11],
        "product_cycle": [4, 6, 8, 18, 4, 6],
        "base_notional": 210_000,
        "account": "000320020001",
        "branch": 202,
        "project_prefix": "ATLAS",
        "tx_count": 18,
        "tx_currency_cycle": ["EUR", "EUR", "USD", "EUR", "USD", "EUR"],
        "tx_type_cycle": ["Receivables", "Device Export", "Equipment Payment", "Revenue Hedge", "Capex", "Clinical Trial Spend"],
    },
    {
        "id": 32003,
        "name": "Cedar Mobility",
        "english": "Cedar Mobility Group",
        "sector": "Retail Mobility",
        "base_currency": 5,
        "deal_count": 16,
        "pair_cycle": ["GBP/ILS", "GBP/ILS", "EUR/ILS", "GBP/ILS", "USD/ILS", "EUR/ILS"],
        "bank_cycle": [2, 26, 11, 34, 2, 26],
        "product_cycle": [4, 8, 6, 18, 4, 6],
        "base_notional": 195_000,
        "account": "000320030001",
        "branch": 303,
        "project_prefix": "CEDAR",
        "tx_count": 16,
        "tx_currency_cycle": ["GBP", "GBP", "EUR", "USD", "EUR"],
        "tx_type_cycle": ["Store Procurement", "Lease Payment", "Spare Parts", "Fleet Hardware", "European Supplier"],
    },
]
