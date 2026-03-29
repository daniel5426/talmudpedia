from __future__ import annotations

from datetime import date, datetime, time, timedelta

from prico_artifact_snapshot_config import SCHEMA_REPORT, TABLES


def parse_columns() -> dict[str, list[tuple[str, str]]]:
    text = SCHEMA_REPORT.read_text(encoding="utf-8")
    lines = text.splitlines()
    parsed: dict[str, list[tuple[str, str]]] = {}
    for table in TABLES:
        start = next(index for index, line in enumerate(lines) if line.strip() == f"### {table}")
        header = next(index for index in range(start, len(lines)) if lines[index].startswith("| # | Column |"))
        rows: list[tuple[str, str]] = []
        for line in lines[header + 2 :]:
            if not line.startswith("|"):
                break
            parts = [part.strip() for part in line.split("|")[1:-1]]
            if len(parts) < 6 or not parts[0].isdigit():
                break
            rows.append((parts[1], parts[2]))
        parsed[table] = rows
    return parsed


COLUMNS = parse_columns()


def default_for_type(data_type: str):
    normalized = data_type.lower()
    if any(token in normalized for token in ("int", "float", "real", "decimal", "numeric", "money")):
        return 0
    if "bit" in normalized:
        return 0
    if "datetime" in normalized:
        return "1901-01-01T00:00:00"
    return ""


def make_row(table: str, overrides: dict) -> dict:
    row = {column: default_for_type(data_type) for column, data_type in COLUMNS[table]}
    row.update(overrides)
    return row


def char8(value: date) -> str:
    return value.strftime("%Y%m%d")


def char12(value: date) -> str:
    return f"{char8(value)}    "


def char6_clock(value: time) -> str:
    return value.strftime("%H%M%S")


def iso_dt(day: date, hour: int, minute: int) -> str:
    return datetime.combine(day, time(hour=hour, minute=minute)).strftime("%Y-%m-%dT%H:%M:%S")


def business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


BENCHMARK_DATES = business_days(date(2026, 2, 10), 26)


def benchmark_average(pair: str, index: int) -> float:
    base = {"USD/ILS": 3.552, "EUR/ILS": 4.091, "GBP/ILS": 4.807}[pair]
    wave = [0.0, 0.012, -0.007, 0.019, -0.013, 0.006, -0.004]
    trend = {"USD/ILS": 0.0008, "EUR/ILS": 0.0012, "GBP/ILS": 0.0015}[pair]
    return round(base + wave[index % len(wave)] + index * trend, 4)


def product_label(code: int) -> str:
    return {4: "Forward", 6: "Spot", 8: "Option", 18: "Option"}.get(code, "FX")


def rate_delta(client_id: int, local_index: int) -> float:
    if local_index % 7 == 4:
        return -0.058 if client_id == 32003 else 0.062
    if local_index % 5 == 1:
        return -0.027 if local_index % 2 else 0.031
    return [-0.009, 0.006, 0.011, -0.004, 0.008][local_index % 5]


def transaction_amount(base: float, index: int) -> float:
    return round(base + ((index % 5) - 2) * 22_500 + (index // 4) * 9_000, 2)
