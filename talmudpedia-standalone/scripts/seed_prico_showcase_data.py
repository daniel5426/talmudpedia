import os
from collections import OrderedDict

import pymssql


CLIENTS = [
    {"id": 32001, "name": "Orion Foods"},
    {"id": 32002, "name": "Atlas Medical"},
    {"id": 32003, "name": "Cedar Mobility"},
]

DEALS = [
    {
        "deal_id": 299101,
        "client_id": 32001,
        "bank_id": 26,
        "date": "20260210",
        "product_code": 6,
        "spot": 3.5510,
        "swap": 0.0030,
        "final_rate": 3.5540,
        "commission_rate": 0.03,
        "commission_amount": 750.0,
        "currency_1": 1,
        "currency_2": 40,
        "paku_date": "2026-02-10 09:10:00",
    },
    {
        "deal_id": 299102,
        "client_id": 32001,
        "bank_id": 2,
        "date": "20260211",
        "product_code": 8,
        "spot": 3.5670,
        "swap": 0.0,
        "final_rate": 3.5810,
        "commission_rate": 0.05,
        "commission_amount": 1800.0,
        "currency_1": 1,
        "currency_2": 40,
        "paku_date": "2026-02-11 10:00:00",
    },
    {
        "deal_id": 299103,
        "client_id": 32001,
        "bank_id": 11,
        "date": "20260212",
        "product_code": 4,
        "spot": 3.5980,
        "swap": 0.0110,
        "final_rate": 3.6090,
        "commission_rate": 0.03,
        "commission_amount": 1050.0,
        "currency_1": 1,
        "currency_2": 40,
        "paku_date": "2026-02-12 11:20:00",
    },
    {
        "deal_id": 299104,
        "client_id": 32001,
        "bank_id": 26,
        "date": "20260213",
        "product_code": 18,
        "spot": 3.5230,
        "swap": 0.0,
        "final_rate": 3.5310,
        "commission_rate": 0.05,
        "commission_amount": 1650.0,
        "currency_1": 1,
        "currency_2": 40,
        "paku_date": "2026-02-13 09:40:00",
    },
    {
        "deal_id": 299105,
        "client_id": 32001,
        "bank_id": 2,
        "date": "20260213",
        "product_code": 6,
        "spot": 3.5410,
        "swap": 0.0020,
        "final_rate": 3.5430,
        "commission_rate": 0.03,
        "commission_amount": 660.0,
        "currency_1": 1,
        "currency_2": 40,
        "paku_date": "2026-02-13 12:05:00",
    },
    {
        "deal_id": 299201,
        "client_id": 32002,
        "bank_id": 11,
        "date": "20260210",
        "product_code": 4,
        "spot": 4.0810,
        "swap": 0.0160,
        "final_rate": 4.0970,
        "commission_rate": 0.03,
        "commission_amount": 960.0,
        "currency_1": 6,
        "currency_2": 40,
        "paku_date": "2026-02-10 14:15:00",
    },
    {
        "deal_id": 299202,
        "client_id": 32002,
        "bank_id": 34,
        "date": "20260211",
        "product_code": 6,
        "spot": 4.0860,
        "swap": 0.0020,
        "final_rate": 4.0880,
        "commission_rate": 0.03,
        "commission_amount": 540.0,
        "currency_1": 6,
        "currency_2": 40,
        "paku_date": "2026-02-11 08:45:00",
    },
    {
        "deal_id": 299203,
        "client_id": 32002,
        "bank_id": 2,
        "date": "20260212",
        "product_code": 8,
        "spot": 4.1180,
        "swap": 0.0,
        "final_rate": 4.1320,
        "commission_rate": 0.05,
        "commission_amount": 1750.0,
        "currency_1": 6,
        "currency_2": 40,
        "paku_date": "2026-02-12 10:35:00",
    },
    {
        "deal_id": 299204,
        "client_id": 32002,
        "bank_id": 11,
        "date": "20260213",
        "product_code": 18,
        "spot": 4.1120,
        "swap": 0.0,
        "final_rate": 4.1210,
        "commission_rate": 0.05,
        "commission_amount": 1625.0,
        "currency_1": 6,
        "currency_2": 40,
        "paku_date": "2026-02-13 11:00:00",
    },
    {
        "deal_id": 299205,
        "client_id": 32002,
        "bank_id": 26,
        "date": "20260213",
        "product_code": 4,
        "spot": 4.0890,
        "swap": 0.0090,
        "final_rate": 4.0980,
        "commission_rate": 0.03,
        "commission_amount": 840.0,
        "currency_1": 6,
        "currency_2": 40,
        "paku_date": "2026-02-13 15:25:00",
    },
    {
        "deal_id": 299301,
        "client_id": 32003,
        "bank_id": 2,
        "date": "20260210",
        "product_code": 4,
        "spot": 4.8010,
        "swap": 0.0120,
        "final_rate": 4.8130,
        "commission_rate": 0.03,
        "commission_amount": 990.0,
        "currency_1": 5,
        "currency_2": 40,
        "paku_date": "2026-02-10 13:05:00",
    },
    {
        "deal_id": 299302,
        "client_id": 32003,
        "bank_id": 26,
        "date": "20260211",
        "product_code": 8,
        "spot": 4.8290,
        "swap": 0.0,
        "final_rate": 4.8420,
        "commission_rate": 0.05,
        "commission_amount": 1875.0,
        "currency_1": 5,
        "currency_2": 40,
        "paku_date": "2026-02-11 09:25:00",
    },
    {
        "deal_id": 299303,
        "client_id": 32003,
        "bank_id": 11,
        "date": "20260212",
        "product_code": 6,
        "spot": 4.7880,
        "swap": 0.0030,
        "final_rate": 4.7910,
        "commission_rate": 0.03,
        "commission_amount": 720.0,
        "currency_1": 5,
        "currency_2": 40,
        "paku_date": "2026-02-12 12:10:00",
    },
    {
        "deal_id": 299304,
        "client_id": 32003,
        "bank_id": 34,
        "date": "20260213",
        "product_code": 18,
        "spot": 4.8160,
        "swap": 0.0,
        "final_rate": 4.8280,
        "commission_rate": 0.05,
        "commission_amount": 1950.0,
        "currency_1": 5,
        "currency_2": 40,
        "paku_date": "2026-02-13 16:40:00",
    },
]

BENCHMARKS = [
    {"pair": "USD/ILS", "curr1": "USD", "curr2": "ILS", "date": "20260210", "avg": 3.5520, "close": 3.5490},
    {"pair": "USD/ILS", "curr1": "USD", "curr2": "ILS", "date": "20260211", "avg": 3.5720, "close": 3.5660},
    {"pair": "USD/ILS", "curr1": "USD", "curr2": "ILS", "date": "20260212", "avg": 3.6050, "close": 3.5980},
    {"pair": "USD/ILS", "curr1": "USD", "curr2": "ILS", "date": "20260213", "avg": 3.5280, "close": 3.5360},
    {"pair": "EUR/ILS", "curr1": "EUR", "curr2": "ILS", "date": "20260210", "avg": 4.0910, "close": 4.0840},
    {"pair": "EUR/ILS", "curr1": "EUR", "curr2": "ILS", "date": "20260211", "avg": 4.0850, "close": 4.0790},
    {"pair": "EUR/ILS", "curr1": "EUR", "curr2": "ILS", "date": "20260212", "avg": 4.1270, "close": 4.1140},
    {"pair": "EUR/ILS", "curr1": "EUR", "curr2": "ILS", "date": "20260213", "avg": 4.1040, "close": 4.1010},
    {"pair": "GBP/ILS", "curr1": "GBP", "curr2": "ILS", "date": "20260210", "avg": 4.8070, "close": 4.7990},
    {"pair": "GBP/ILS", "curr1": "GBP", "curr2": "ILS", "date": "20260211", "avg": 4.8360, "close": 4.8210},
    {"pair": "GBP/ILS", "curr1": "GBP", "curr2": "ILS", "date": "20260212", "avg": 4.7860, "close": 4.7810},
    {"pair": "GBP/ILS", "curr1": "GBP", "curr2": "ILS", "date": "20260213", "avg": 4.8240, "close": 4.8180},
]


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
