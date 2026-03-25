from __future__ import annotations

import os
from collections import OrderedDict

import pymssql

from prico_showcase_seed_data import BENCHMARKS, CLIENTS, DEALS


def connect():
    return pymssql.connect(
        server=f"{os.getenv('PRICO_DB_HOST', '127.0.0.1')}:{os.getenv('PRICO_DB_PORT', '1433')}",
        user=os.getenv("PRICO_DB_USER", "ui_test"),
        password=os.getenv("PRICO_DB_PASSWORD", "UiTest12345"),
        database=os.getenv("PRICO_DB_DATABASE", "PricoDBForAI"),
        charset="UTF-8",
    )


def insert_clients(cursor):
    client_ids = [client["id"] for client in CLIENTS]
    cursor.execute(
        f"DELETE FROM prico.lekohot WHERE mispar_lakoah IN ({', '.join(['%s'] * len(client_ids))})",
        tuple(client_ids),
    )
    for client in CLIENTS:
        cursor.execute(
            "INSERT INTO prico.lekohot (mispar_lakoah, shem_lakoah) VALUES (%s, %s)",
            (client["id"], client["name"]),
        )


def insert_deals(cursor):
    deal_ids = [deal["deal_id"] for deal in DEALS]
    params = tuple(deal_ids)
    placeholders = ", ".join(["%s"] * len(deal_ids))
    cursor.execute(f"DELETE FROM prico.paku WHERE iska IN ({placeholders})", params)
    cursor.execute(f"DELETE FROM prico.nigrarot_bankaiyot WHERE ishur_iska IN ({placeholders})", params)
    cursor.execute(f"DELETE FROM prico.iskaot WHERE ishur_iska IN ({placeholders})", params)

    for deal in DEALS:
        cursor.execute(
            """
            INSERT INTO prico.iskaot (
              ishur_iska,
              lakoah_mispar,
              mispar_bank,
              taharich_bitzua,
              taharich_rishum,
              taharich_aklada_aharon,
              modify_date,
              taharich_shinui,
              taharich_ashinui,
              sug_iska,
              shahar_sofi,
              spot,
              svop,
              sheur_amlat_lakoah,
              amlat_lakoah
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                deal["deal_id"],
                deal["client_id"],
                deal["bank_id"],
                f"{deal['date']}    ",
                f"{deal['date']}    ",
                f"{deal['date']}    ",
                f"{deal['date']}    ",
                f"{deal['date']}    ",
                f"{deal['date']}    ",
                deal["product_code"],
                deal["final_rate"],
                deal["spot"],
                deal["swap"],
                deal["commission_rate"],
                deal["commission_amount"],
            ),
        )
        cursor.execute(
            """
            INSERT INTO prico.nigrarot_bankaiyot (
              ishur_iska,
              code_matbea_1_1,
              code_matbea_1_2,
              total_1_1,
              total_1_2,
              mimush_1,
              spot_1,
              principal_amount
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                deal["deal_id"],
                deal["currency_1"],
                deal["currency_2"],
                round((deal["commission_amount"] / deal["commission_rate"]) * 10, 2),
                round((deal["commission_amount"] / deal["commission_rate"]) * 10 * deal["final_rate"], 2),
                deal["final_rate"],
                deal["spot"],
                round((deal["commission_amount"] / deal["commission_rate"]) * 10, 2),
            ),
        )
        cursor.execute(
            "INSERT INTO prico.paku (iska, paka, datee, meadcen) VALUES (%s, %s, %s, %s)",
            (deal["deal_id"], True, deal["paku_date"], "SHOWCASE"),
        )


def insert_benchmarks(cursor):
    unique_keys = OrderedDict()
    for benchmark in BENCHMARKS:
        unique_keys[(benchmark["pair"], benchmark["date"])] = benchmark

    for pair, date in unique_keys:
        cursor.execute(
            "DELETE FROM dbo.CurrencyPairsHistory WHERE PairName = %s AND LastDate = %s",
            (pair, date),
        )

    for benchmark in unique_keys.values():
        avg = benchmark["avg"]
        close = benchmark["close"]
        cursor.execute(
            """
            INSERT INTO dbo.CurrencyPairsHistory (
              PairName,
              Curr1,
              Curr2,
              Bid,
              Ask,
              High,
              Low,
              OpenValue,
              LastCloseValue,
              Change,
              ChangePercent,
              LastDate,
              LastTime,
              BidAskAverage
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                benchmark["pair"],
                benchmark["curr1"],
                benchmark["curr2"],
                avg - 0.005,
                avg + 0.005,
                avg + 0.02,
                avg - 0.02,
                close,
                close,
                avg - close,
                round(((avg - close) / close) * 100, 4),
                benchmark["date"],
                "120000",
                avg,
            ),
        )


def main():
    connection = connect()
    try:
        with connection.cursor() as cursor:
            insert_clients(cursor)
            insert_deals(cursor)
            insert_benchmarks(cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"Seeded {len(CLIENTS)} showcase clients, {len(DEALS)} deals, and {len(BENCHMARKS)} benchmark rows.")


if __name__ == "__main__":
    main()
