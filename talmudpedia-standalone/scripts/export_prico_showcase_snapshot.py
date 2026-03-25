from __future__ import annotations

import json
from pathlib import Path

from prico_showcase_seed_data import BANKS, BENCHMARKS, CLIENTS, CURRENCIES, DEALS, SSARS


ROOT = Path(__file__).resolve().parent.parent / "server" / "prico-demo" / "frozen_snapshot"


def _date_char(value: str) -> str:
    return f"{value}    "


def _notional_proxy(deal: dict) -> float:
    return round((deal["commission_amount"] / deal["commission_rate"]) * 10, 2)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _lekohot_rows() -> list[dict]:
    return [
        {
            "mispar_lakoah": client["id"],
            "shem_lakoah": client["name"],
        }
        for client in CLIENTS
    ]


def _iskaot_rows() -> list[dict]:
    rows: list[dict] = []
    for deal in DEALS:
        rows.append(
            {
                "ishur_iska": deal["deal_id"],
                "lakoah_mispar": deal["client_id"],
                "mispar_bank": deal["bank_id"],
                "taharich_bitzua": _date_char(deal["date"]),
                "taharich_rishum": _date_char(deal["date"]),
                "taharich_aklada_aharon": _date_char(deal["date"]),
                "modify_date": _date_char(deal["date"]),
                "taharich_shinui": _date_char(deal["date"]),
                "taharich_ashinui": _date_char(deal["date"]),
                "sug_iska": deal["product_code"],
                "shahar_sofi": deal["final_rate"],
                "spot": deal["spot"],
                "svop": deal["swap"],
                "sheur_amlat_lakoah": deal["commission_rate"],
                "amlat_lakoah": deal["commission_amount"],
            }
        )
    return rows


def _nigrarot_rows() -> list[dict]:
    rows: list[dict] = []
    for deal in DEALS:
        total_1 = _notional_proxy(deal)
        rows.append(
            {
                "ishur_iska": deal["deal_id"],
                "code_matbea_1_1": deal["currency_1"],
                "code_matbea_1_2": deal["currency_2"],
                "total_1_1": total_1,
                "total_1_2": round(total_1 * deal["final_rate"], 2),
                "mimush_1": deal["final_rate"],
                "spot_1": deal["spot"],
                "principal_amount": total_1,
            }
        )
    return rows


def _paku_rows() -> list[dict]:
    return [
        {
            "iska": deal["deal_id"],
            "paka": 1,
            "datee": deal["paku_date"],
            "meadcen": "SHOWCASE",
        }
        for deal in DEALS
    ]


def _benchmark_rows() -> list[dict]:
    rows: list[dict] = []
    for benchmark in BENCHMARKS:
        avg = benchmark["avg"]
        close = benchmark["close"]
        rows.append(
            {
                "PairName": benchmark["pair"],
                "Curr1": benchmark["curr1"],
                "Curr2": benchmark["curr2"],
                "Bid": round(avg - 0.005, 4),
                "Ask": round(avg + 0.005, 4),
                "High": round(avg + 0.02, 4),
                "Low": round(avg - 0.02, 4),
                "OpenValue": close,
                "LastCloseValue": close,
                "Change": round(avg - close, 4),
                "ChangePercent": round(((avg - close) / close) * 100, 4),
                "LastDate": benchmark["date"],
                "LastTime": "120000",
                "BidAskAverage": avg,
            }
        )
    return rows


def main() -> None:
    _write_json(
        ROOT / "snapshot_manifest.json",
        {
            "snapshot_name": "prico_showcase_v1",
            "generated_from": "talmudpedia-standalone/scripts/prico_showcase_seed_data.py",
            "generated_for": "artifact-backed Prico demo tools",
            "notes": [
                "Rows are table-shaped snapshots intended to stay close to the live PRICO demo schema.",
                "Only the tables and columns used by the current PRICO standalone tools are included.",
                "bankim, matbeot, and ssars include curated demo rows needed by the frozen artifact demo.",
            ],
            "tables": {
                "prico.lekohot": len(CLIENTS),
                "prico.iskaot": len(DEALS),
                "prico.bankim": len(BANKS),
                "prico.matbeot": len(CURRENCIES),
                "prico.nigrarot_bankaiyot": len(DEALS),
                "prico.paku": len(DEALS),
                "prico.ssars": len(SSARS),
                "dbo.CurrencyPairsHistory": len(BENCHMARKS),
            },
        },
    )
    _write_json(ROOT / "prico" / "lekohot.json", _lekohot_rows())
    _write_json(ROOT / "prico" / "iskaot.json", _iskaot_rows())
    _write_json(ROOT / "prico" / "bankim.json", BANKS)
    _write_json(ROOT / "prico" / "matbeot.json", CURRENCIES)
    _write_json(ROOT / "prico" / "nigrarot_bankaiyot.json", _nigrarot_rows())
    _write_json(ROOT / "prico" / "paku.json", _paku_rows())
    _write_json(ROOT / "prico" / "ssars.json", SSARS)
    _write_json(ROOT / "dbo" / "CurrencyPairsHistory.json", _benchmark_rows())
    print(f"Wrote frozen snapshot to {ROOT}")


if __name__ == "__main__":
    main()
