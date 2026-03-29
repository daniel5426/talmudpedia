from __future__ import annotations

import json
from datetime import date, time, timedelta
from pathlib import Path

from prico_artifact_snapshot_config import BANKS, CLIENTS, CURRENCIES, JSON_ROOT, PAIR_TO_CODES, PAIR_TO_IDS, ROOT
from prico_artifact_snapshot_utils import (
    BENCHMARK_DATES,
    benchmark_average,
    business_days,
    char12,
    char6_clock,
    char8,
    iso_dt,
    make_row,
    product_label,
    rate_delta,
    transaction_amount,
)




def bank_name(bank_id: int) -> str:
    return next(bank["Teur_English"] for bank in BANKS if bank["mispar_bank"] == bank_id)


def build_client_rows() -> list[dict]:
    rows: list[dict] = []
    for index, client in enumerate(CLIENTS, start=1):
        rows.append(
            make_row(
                "prico.lekohot",
                {
                    "shem_lakoah": client["name"],
                    "mispar_lakoah": client["id"],
                    "siha_im": "Treasury Lead",
                    "ctovet": f"{10 + index} Market Street, Tel Aviv",
                    "phone": f"03-7000{index:03d}",
                    "fax": "",
                    "code_kvutza": 1,
                    "natzig": "Dana Levi",
                    "tafkid": "CFO",
                    "schum_misgeret": 2_500_000 + index * 350_000,
                    "sug_peilut": client["sector"],
                    "taharich_youledet": "20240101    ",
                    "earot": f"{client['sector']} showcase customer with mixed hedge scenarios.",
                    "status": "A",
                    "natzig_prico": 10 + index,
                    "mispar_anhash": 1000 + index,
                    "kvutzat_shiuh": 1,
                    "matbea_ogen": client["base_currency"],
                    "code_sug_peilut": 1 + index,
                    "mamlitz": 1,
                    "email": f"{client['name'].lower().replace(' ', '.')}@demo.local",
                    "dmey_riteyner": 4_500 + index * 250,
                    "from_date": "20260101    ",
                    "to_date": "20261231    ",
                    "sug_sherut": 1,
                    "matbea1": client["base_currency"],
                    "mehir": 0,
                    "earot_mehir": "",
                    "oraot_lakoah": "Follow benchmark discipline and confirmation SLA.",
                    "nitzul_misgeret": 0.42 + index * 0.08,
                    "sug_lakoah": 2,
                    "city": 500 + index,
                    "F_U": "SHOWCASE",
                    "shyuch": 1,
                    "taharich_shyuch": "20260101    ",
                    "meadken_s": "SHOWCASE",
                    "tz_comp": 510000000 + index,
                    "min": 1,
                    "leda": "2024-01-01T09:00:00",
                    "bank_s": float(index),
                    "saot_senutsal": 0,
                    "saot_me": "2026-02-10T08:00:00",
                    "saot_ad": "2026-03-31T18:00:00",
                    "saot_pail": 1,
                    "nene": 0,
                    "kod_medina": 972,
                    "sug_kasur": 0,
                    "maamad_l": 1,
                    "uva": 1,
                    "dateuva": "2026-01-05T11:00:00",
                    "lakpi": 1,
                    "laknpi": client["english"],
                    "englishname": client["english"],
                    "lpail": "ACTIVE",
                    "mesuyach": 1,
                    "migzar": index,
                    "tosvut": 0,
                    "s1": 1,
                    "s2": 0,
                    "s3": 0,
                    "s4": 0,
                    "s5": 0,
                    "s6": 0,
                    "historia": 1,
                    "ComissionTypeID": 1,
                    "FrequencyID": 1,
                    "AlarmDays": 3,
                    "Mikud": 6100000 + index,
                    "RefusalTypeReason": 0,
                    "ExternalAccountsID": f"EXT-{client['id']}",
                    "HashDocumentTypeID": 1,
                },
            )
        )
    return rows


def build_benchmark_rows() -> list[dict]:
    rows: list[dict] = []
    for pair in PAIR_TO_IDS:
        curr1, curr2 = PAIR_TO_CODES[pair]
        for index, day in enumerate(BENCHMARK_DATES):
            avg = benchmark_average(pair, index)
            close = round(avg - 0.004 + ((index % 3) * 0.002), 4)
            rows.append(
                make_row(
                    "dbo.CurrencyPairsHistory",
                    {
                        "PairName": pair,
                        "Curr1": curr1,
                        "Curr2": curr2,
                        "Bid": round(avg - 0.005, 4),
                        "Ask": round(avg + 0.005, 4),
                        "High": round(avg + 0.021, 4),
                        "Low": round(avg - 0.019, 4),
                        "OpenValue": close,
                        "LastCloseValue": close,
                        "Change": round(avg - close, 4),
                        "ChangePercent": round(((avg - close) / close) * 100, 4),
                        "LastDate": char8(day),
                        "LastTime": "120000",
                        "BidAskAverage": avg,
                    },
                )
            )
    return rows


def build_deal_blueprints() -> list[dict]:
    blueprints: list[dict] = []
    date_offsets = {32001: 0, 32002: 2, 32003: 4}
    next_deal_id = 299101
    for client in CLIENTS:
        dates = BENCHMARK_DATES[date_offsets[client["id"]] : date_offsets[client["id"]] + client["deal_count"]]
        for local_index in range(client["deal_count"]):
            pair = client["pair_cycle"][local_index % len(client["pair_cycle"])]
            bank_id = client["bank_cycle"][local_index % len(client["bank_cycle"])]
            product_code = client["product_cycle"][local_index % len(client["product_cycle"])]
            trade_day = dates[local_index]
            benchmark_idx = BENCHMARK_DATES.index(trade_day)
            benchmark = benchmark_average(pair, benchmark_idx)
            delta = rate_delta(client["id"], local_index)
            swap = round(0.0 if product_code in (8, 18) else 0.002 + (local_index % 4) * 0.003, 4)
            final_rate = round(benchmark + delta, 4)
            spot = round(final_rate - swap, 4)
            notional = transaction_amount(client["base_notional"], local_index)
            commission_rate = 0.05 if product_code in (8, 18) else 0.03
            commission_amount = round(notional * commission_rate / 10, 2)
            settlement_day = trade_day + timedelta(days=21 + (local_index % 4) * 14)
            has_paku = local_index % 6 != 2
            has_ssars = product_code in (8, 18) or local_index % 5 == 0
            has_customer_confirmation = local_index % 9 != 4
            has_bank_confirmation = local_index % 8 != 3
            hedge_effective = 0 if local_index % 5 == 2 else 1
            change_count = 3 if local_index % 6 == 1 else (2 if local_index % 5 == 3 else (1 if local_index % 4 == 0 else 0))
            yoman_status = ["F", "A", "F", "E", "F", "C"][local_index % 6]
            disruption = 1 if abs(delta) >= 0.05 and local_index % 2 == 0 else 0
            pair_curr_1, pair_curr_2 = PAIR_TO_IDS[pair]
            blueprints.append(
                {
                    "deal_id": next_deal_id,
                    "client_id": client["id"],
                    "client_name": client["name"],
                    "bank_id": bank_id,
                    "pair": pair,
                    "currency_1": pair_curr_1,
                    "currency_2": pair_curr_2,
                    "trade_day": trade_day,
                    "settlement_day": settlement_day,
                    "product_code": product_code,
                    "spot": spot,
                    "swap": swap,
                    "final_rate": final_rate,
                    "benchmark_rate": benchmark,
                    "notional": notional,
                    "commission_rate": commission_rate,
                    "commission_amount": commission_amount,
                    "has_paku": has_paku,
                    "has_ssars": has_ssars,
                    "has_customer_confirmation": has_customer_confirmation,
                    "has_bank_confirmation": has_bank_confirmation,
                    "hedge_effective": hedge_effective,
                    "hedge_number": client["id"] * 10 + local_index // 2,
                    "change_count": change_count,
                    "yoman_status": yoman_status,
                    "disruption": disruption,
                    "project_number": f"{client['project_prefix']}-{local_index + 1:03d}",
                    "account": client["account"],
                    "branch": client["branch"],
                }
            )
            next_deal_id += 1
    return blueprints


def build_transaction_rows() -> list[dict]:
    rows: list[dict] = []
    next_id = 1
    create_day = date(2026, 2, 15)
    future_starts = business_days(date(2026, 4, 1), 40)
    for client in CLIENTS:
        for index in range(client["tx_count"]):
            currency = client["tx_currency_cycle"][index % len(client["tx_currency_cycle"])]
            from_day = future_starts[index]
            to_day = from_day + timedelta(days=14 + (index % 3) * 14)
            amount = transaction_amount(client["base_notional"] * 0.85, index)
            target_rate = round(benchmark_average(f"{currency}/ILS", index % len(BENCHMARK_DATES)) + (0.01 if index % 4 == 0 else 0.0), 4)
            rows.append(
                make_row(
                    "dbo.CustomerTransactions",
                    {
                        "ID": next_id,
                        "CustomerID": client["id"],
                        "TransactionDate": char8(create_day + timedelta(days=index)),
                        "TransactionType": client["tx_type_cycle"][index % len(client["tx_type_cycle"])],
                        "TransactionTarget": f"{client['project_prefix']} cash flow {index + 1}",
                        "CurrencyID": currency,
                        "AmountInCurrency": amount,
                        "TargetRate": target_rate,
                        "TransactionPurposeID": f"PURPOSE-{(index % 4) + 1}",
                        "HedgePercent": [35.0, 50.0, 65.0, 80.0][index % 4],
                        "SupplierName": f"{client['project_prefix']} counterparty {index % 6 + 1}",
                        "SupplierTransactionID": f"{client['project_prefix']}-TX-{next_id:03d}",
                        "DegreeOfCertainty": [0.55, 0.7, 0.82, 0.95][index % 4],
                        "FromDate": char8(from_day),
                        "ToDate": char8(to_day),
                        "Expense_Income": 2 if client["id"] == 32002 and currency == "EUR" else 1,
                        "Remarks": "Generated future obligation row for hedge coverage demo.",
                        "CreateDate": char8(create_day),
                        "CreateUserID": 9001,
                    },
                )
            )
            next_id += 1
    return rows


def build_snapshot() -> dict[str, list[dict]]:
    benchmark_rows = build_benchmark_rows()
    benchmark_lookup = {
        (row["PairName"], row["LastDate"]): row["BidAskAverage"] for row in benchmark_rows
    }
    deals = build_deal_blueprints()

    snapshot: dict[str, list[dict]] = {
        "prico.bankim": [make_row("prico.bankim", bank) for bank in BANKS],
        "prico.lekohot": build_client_rows(),
        "prico.matbeot": [make_row("prico.matbeot", currency) for currency in CURRENCIES],
        "prico.iskaot": [],
        "prico.nigrarot_bankaiyot": [],
        "prico.paku": [],
        "prico.ssars": [],
        "prico.yoman": [],
        "dbo.CurrencyPairsHistory": benchmark_rows,
        "dbo.CustomerTransactions": build_transaction_rows(),
        "dbo.DealsConfirmations": [],
        "dbo.DealChangesLogHeaders": [],
        "dbo.DealChangesLogLines": [],
    }

    yoman_line = 1
    change_serial = 1
    for deal in deals:
        trade_day = deal["trade_day"]
        settlement_day = deal["settlement_day"]
        trade_date = char8(trade_day)
        trade_char = char12(trade_day)
        settle_char = char12(settlement_day)
        trade_time = time(hour=9 + (deal["deal_id"] % 7), minute=(deal["deal_id"] * 7) % 60)
        delta = round(deal["final_rate"] - deal["benchmark_rate"], 4)
        customer_saving = max(0.0, round(abs(delta) * deal["notional"] * 0.04, 2))
        confirmation_date = char8(trade_day + timedelta(days=1))
        snapshot["prico.iskaot"].append(
            make_row(
                "prico.iskaot",
                {
                    "ishur_iska": deal["deal_id"],
                    "mispar_bank": deal["bank_id"],
                    "mispar_snif": deal["branch"],
                    "mispar_heshbon": deal["account"],
                    "yoman_mispar": yoman_line,
                    "iska_mispar": str(deal["deal_id"])[-7:],
                    "lakoah_mispar": deal["client_id"],
                    "matzav": "A" if deal["yoman_status"] != "C" else "C",
                    "pnimi": deal["deal_id"] * 10,
                    "emtzai_bitzua": 1,
                    "taharich_bitzua": trade_char,
                    "shaha": char6_clock(trade_time),
                    "akavnu_bitzanu": "B",
                    "mimush_betaharich": settle_char,
                    "mesira_betaharich": settle_char,
                    "sheur_amlat_lakoah": deal["commission_rate"],
                    "amlat_lakoah": deal["commission_amount"],
                    "matbea_amlat_lakoah": deal["currency_2"],
                    "sheur_amlat_broker": 0.01,
                    "amalat_broker": round(deal["commission_amount"] * 0.28, 2),
                    "matbea_amlat_broker": deal["currency_2"],
                    "sheur_amla_bank": 0.008,
                    "amla_bank": round(deal["commission_amount"] * 0.22, 2),
                    "matbea_amlat_bank": deal["currency_2"],
                    "sheur_amlat_nefach": 0,
                    "amlat_nefah": 0,
                    "matbea_amlat_nefah": deal["currency_2"],
                    "sheur_amlat_metaveh": 0,
                    "amlat_metaveh": 0,
                    "matbea_amlat_metaveh": deal["currency_2"],
                    "sheur_amla_meyuhedet": 0,
                    "amla_meyuhedet": 0,
                    "matbea_amla_meyuhedet": deal["currency_2"],
                    "sug_iska": deal["product_code"],
                    "sug_iska_2": "",
                    "spot": deal["spot"],
                    "svop": deal["swap"],
                    "mimun": 0,
                    "amlat_abank": round(deal["commission_amount"] * 0.15, 2),
                    "amlat_broker": round(deal["commission_amount"] * 0.28, 2),
                    "shahar_sofi": deal["final_rate"],
                    "earot": f"{product_label(deal['product_code'])} showcase deal via {bank_name(deal['bank_id'])}.",
                    "taharich_rishum": trade_char,
                    "hatimat_mebatzea_iska": "SHOWCASE",
                    "hatimat_bodek": "QA",
                    "sharuh_spot": deal["spot"],
                    "shiaruh_svop": deal["swap"],
                    "shiaruh_mimun": 0,
                    "shiaruh_amlat_bank": round(deal["commission_amount"] * 0.22, 2),
                    "shiharuh_amlat_broker": round(deal["commission_amount"] * 0.28, 2),
                    "shiaruh_shahar_sofi": deal["final_rate"],
                    "tupal_al_yedey": "SHOWCASE",
                    "shulam_broker": "0",
                    "shulam_lakoah": "1",
                    "shulam_bank": "0",
                    "shulam_nefah": "0",
                    "shulam_metaveh": "0",
                    "shulam_meyuhedet": "0",
                    "matbea_rishon": deal["currency_1"],
                    "taharich_aklada_aharon": trade_char,
                    "kniya_mehira_op7": "B" if deal["product_code"] in (8, 18) else "",
                    "ragil_tzelinder_op8": "R",
                    "zihui_tzelinder": 1,
                    "ishur_bank_itkabel": "1" if deal["has_bank_confirmation"] else "0",
                    "taharich_kabalat_ishur": confirmation_date + "    " if deal["has_bank_confirmation"] else "",
                    "shahat_kabalat_ishur": "103000" if deal["has_bank_confirmation"] else "",
                    "shem_mekabel_ishur": "BANKOPS" if deal["has_bank_confirmation"] else "",
                    "yes_no_1": "0",
                    "yes_no_2": "0",
                    "sug_mimush": "S",
                    "ishur": 1,
                    "taharich_ishur": trade_char,
                    "diler_bank_name": bank_name(deal["bank_id"])[:10],
                    "shem_mehasher": "SHOW",
                    "modify_date": trade_char,
                    "amlat_bank": round(deal["commission_amount"] * 0.22, 2),
                    "user_name_shinui": "SHOWCASE",
                    "taharich_ashinui": trade_char,
                    "shiuch_iska_tzad_c": "",
                    "mispar_lakoah_tzad_c": 0,
                    "mispar_iska_tzad_c": "",
                    "earot_amla": "",
                    "F_U": "SHOWCASE",
                    "yahad_ahasaka": 0,
                    "user_name": "SHOWCASE",
                    "taharich_shinui": trade_char,
                    "premia_f": round(deal["notional"] * 0.0018, 2) if deal["product_code"] in (8, 18) else 0,
                    "mekasher": 100 + (deal["deal_id"] % 7),
                    "yeutsl": "",
                    "date_or_la": iso_dt(trade_day, 9, 15),
                    "date_or_pr": iso_dt(trade_day, 9, 20),
                    "migbalats": round(deal["notional"] * 0.1, 2),
                    "r4": "",
                    "r5": "",
                    "r6": "",
                    "r7": "",
                    "r8": "",
                    "t1": 0,
                    "t2": 0,
                    "t3": 0,
                    "t4": 0,
                    "t5": 0,
                    "t6": 0,
                    "t7": 0,
                    "StatusTipulBaIska": 4 if deal["yoman_status"] == "E" else 2,
                    "sugi": "F",
                    "Done": 0 if deal["yoman_status"] in ("A", "E") else 1,
                    "DoneDate": char8(trade_day + timedelta(days=1)),
                    "DoneTime": "110000",
                    "DoneUserID": 9001,
                    "SentReminderToCustomer": 1 if not deal["has_customer_confirmation"] else 0,
                    "SentAlertSmsToCustomer": 1 if deal["yoman_status"] == "E" else 0,
                    "SentAlertMailToCustomer": 1 if deal["yoman_status"] in ("E", "C") else 0,
                    "BloombergLegNumber": 1,
                    "BloombergCustomerName": deal["client_name"],
                    "SpotSaving": customer_saving,
                    "SwapSaving": round(customer_saving * 0.22, 2),
                    "FundingSaving": round(customer_saving * 0.08, 2),
                    "TotalCustomerSaving": round(customer_saving * 1.3, 2),
                    "AmountToRecalculate": "0",
                    "hedgeNumber": deal["hedge_number"],
                    "hedgePeriod": char8(settlement_day),
                    "hedgeEffective": deal["hedge_effective"],
                    "DealState": 1 if deal["yoman_status"] != "C" else 3,
                    "DealCancelDate": char8(trade_day + timedelta(days=2)) if deal["yoman_status"] == "C" else "",
                    "DealCancelUserID": 9001 if deal["yoman_status"] == "C" else 0,
                    "DealCancelReason": "Customer withdrew order" if deal["yoman_status"] == "C" else "",
                    "DivuachHalbanatHon": 0,
                    "PrintSaving": 1,
                    "bid": round(deal["benchmark_rate"] - 0.006, 4),
                    "ask": round(deal["benchmark_rate"] + 0.006, 4),
                    "high": round(deal["benchmark_rate"] + 0.02, 4),
                    "low": round(deal["benchmark_rate"] - 0.02, 4),
                    "LastCloseValue": round(deal["benchmark_rate"] - 0.004, 4),
                    "NotForChargeReason": 0,
                    "disruption": deal["disruption"],
                    "disruption_type": 2 if deal["disruption"] else 0,
                    "disruption_rate": round(abs(delta), 4) if deal["disruption"] else 0,
                    "disruption_date": char8(trade_day) if deal["disruption"] else "",
                    "disruption_user_id": 9002 if deal["disruption"] else 0,
                    "customer_saving_currency_code": deal["currency_1"],
                    "disruption_time": "114500" if deal["disruption"] else "",
                    "CCS": 0,
                    "CCSBillingFreqType": 0,
                    "CCSBuyInterestType": 0,
                    "CCSBuyInterestRate": 0,
                    "CCSSellInterestType": 0,
                    "CCSSellInterestRate": 0,
                    "CCSFinancialMarginPercentSell": 0,
                    "CCSFinancialMarginPercentBuy": 0,
                    "CC": 0,
                    "CustomerProjectNumber": deal["project_number"],
                    "Commission": deal["commission_amount"],
                    "CommissionDiscount": round(deal["commission_amount"] * 0.08, 2),
                },
            )
        )

        snapshot["prico.nigrarot_bankaiyot"].append(
            make_row(
                "prico.nigrarot_bankaiyot",
                {
                    "ishur_iska": deal["deal_id"],
                    "sug_1": "F",
                    "sug_iska": deal["product_code"],
                    "kniya_mehira_1": "B",
                    "mimush_1": deal["final_rate"],
                    "spot_1": deal["spot"],
                    "put_call_1_1": "C" if deal["product_code"] in (8, 18) else "",
                    "code_matbea_1_1": deal["currency_1"],
                    "total_1_1": deal["notional"],
                    "kamut_beyehida": 1,
                    "put_call_1_2": "",
                    "code_matbea_1_2": deal["currency_2"],
                    "total_1_2": round(deal["notional"] * deal["final_rate"], 2),
                    "premya_1": round(deal["notional"] * 0.002, 2) if deal["product_code"] in (8, 18) else 0,
                    "premya_1_code_matbea": deal["currency_2"],
                    "amla_1": round(deal["commission_amount"] * 0.5, 2),
                    "amla_1_code_matbea": deal["currency_2"],
                    "sug_2": "",
                    "kniya_mehira_2": "",
                    "mimush_2": 0,
                    "spot_2": 0,
                    "put_call_2_1": "",
                    "code_matbea_2_1": 0,
                    "kamut_2_1": 0,
                    "put_call_2_2": "",
                    "code_matbea_2_2": 0,
                    "kamut_2_2": 0,
                    "premya_2": 0,
                    "premya_2_code_matbea": 0,
                    "amla_2": 0,
                    "amla_2_code_matbea": 0,
                    "total_premya": round(deal["notional"] * 0.002, 2) if deal["product_code"] in (8, 18) else 0,
                    "code_matbea_total_premya": deal["currency_2"],
                    "total_amla": deal["commission_amount"],
                    "code_matbea_total_amla": deal["currency_2"],
                    "gvul_1": round(deal["final_rate"] * 1.02, 4),
                    "inout1": "IN",
                    "gvul_2": round(deal["final_rate"] * 0.98, 4),
                    "inout2": "OUT",
                    "taharich_dgima": trade_char,
                    "f_u": "SHOW",
                    "iska_ribiot": 0,
                    "mesira_date": iso_dt(settlement_day, 12, 0),
                    "flow_type": "PRIMARY",
                    "principal_amount": deal["notional"],
                    "startday": iso_dt(trade_day, 9, 0),
                    "enddate": iso_dt(settlement_day, 12, 0),
                    "dayst": (settlement_day - trade_day).days,
                    "cash_flow": round(deal["notional"] * 0.1, 2),
                    "rate": round(deal["final_rate"], 4),
                    "sugr": 0,
                    "libor_interest": 0,
                    "livor_sug": 0,
                },
            )
        )

        if deal["product_code"] in (8, 18) or deal["deal_id"] % 6 == 0:
            snapshot["prico.nigrarot_bankaiyot"].append(
                make_row(
                    "prico.nigrarot_bankaiyot",
                    {
                        "ishur_iska": deal["deal_id"],
                        "sug_1": "F",
                        "sug_iska": deal["product_code"],
                        "kniya_mehira_1": "S",
                        "mimush_1": round(deal["final_rate"] * 1.005, 4),
                        "spot_1": deal["spot"],
                        "put_call_1_1": "P" if deal["product_code"] in (8, 18) else "",
                        "code_matbea_1_1": deal["currency_1"],
                        "total_1_1": round(deal["notional"] * 0.42, 2),
                        "kamut_beyehida": 1,
                        "put_call_1_2": "",
                        "code_matbea_1_2": deal["currency_2"],
                        "total_1_2": round(deal["notional"] * deal["final_rate"] * 0.42, 2),
                        "premya_1": round(deal["notional"] * 0.0011, 2),
                        "premya_1_code_matbea": deal["currency_2"],
                        "amla_1": round(deal["commission_amount"] * 0.22, 2),
                        "amla_1_code_matbea": deal["currency_2"],
                        "total_premya": round(deal["notional"] * 0.0011, 2),
                        "code_matbea_total_premya": deal["currency_2"],
                        "total_amla": round(deal["commission_amount"] * 0.22, 2),
                        "code_matbea_total_amla": deal["currency_2"],
                        "gvul_1": round(deal["final_rate"] * 1.03, 4),
                        "inout1": "IN",
                        "gvul_2": round(deal["final_rate"] * 0.97, 4),
                        "inout2": "OUT",
                        "taharich_dgima": char12(trade_day + timedelta(days=1)),
                        "f_u": "SHOW",
                        "mesira_date": iso_dt(settlement_day + timedelta(days=7), 12, 0),
                        "flow_type": "FOLLOWUP",
                        "principal_amount": round(deal["notional"] * 0.42, 2),
                        "startday": iso_dt(trade_day + timedelta(days=1), 9, 0),
                        "enddate": iso_dt(settlement_day + timedelta(days=7), 12, 0),
                        "dayst": (settlement_day - trade_day).days + 7,
                        "cash_flow": round(deal["notional"] * 0.06, 2),
                        "rate": round(deal["final_rate"] * 1.005, 4),
                    },
                )
            )

        if deal["has_paku"]:
            snapshot["prico.paku"].append(
                make_row(
                    "prico.paku",
                    {
                        "iska": deal["deal_id"],
                        "paka": 1,
                        "datee": iso_dt(trade_day, 10, 15),
                        "meadcen": "SHOWCASE",
                    },
                )
            )

        if deal["has_ssars"]:
            snapshot["prico.ssars"].append(
                make_row(
                    "prico.ssars",
                    {
                        "iska": deal["deal_id"],
                        "saar": round(delta * 10000, 2),
                        "dates": iso_dt(trade_day + timedelta(days=2), 11, 30),
                        "times": "113000",
                        "mevats": "SHOWCASE",
                        "CloseDeal": 1 if deal["yoman_status"] == "F" else 0,
                    },
                )
            )

        snapshot["prico.yoman"].append(
            make_row(
                "prico.yoman",
                {
                    "LineNumber": yoman_line,
                    "taharich_bitzua": iso_dt(trade_day, trade_time.hour, trade_time.minute),
                    "mispar_bank": deal["bank_id"],
                    "mispar_lakoah": deal["client_id"],
                    "matbea_lerehisha": deal["currency_1"],
                    "kamut_rehisha": round(deal["notional"]),
                    "matbea_mehira": deal["currency_2"],
                    "kamut_mehira": round(deal["notional"] * deal["final_rate"]),
                    "spot_limit": deal["spot"],
                    "SwapRate": deal["swap"],
                    "LastRate": deal["final_rate"],
                    "Branch": str(deal["branch"]),
                    "Acount": deal["account"],
                    "shat_mesira": char6_clock(trade_time),
                    "status_limit": deal["yoman_status"],
                    "end_limit": settle_char,
                    "end_time_limit": "170000",
                    "limit_place": "D",
                    "get_limit": "SHOWCASE",
                    "expirity": iso_dt(settlement_day, 17, 0),
                    "DealKind": product_label(deal["product_code"]),
                    "FXNumber": deal["deal_id"],
                    "date_cancel_limit": iso_dt(trade_day + timedelta(days=2), 14, 0) if deal["yoman_status"] == "C" else "",
                    "time_cansel_limit": "140000" if deal["yoman_status"] == "C" else "",
                    "name_get_cansel_limit": "CLIENT" if deal["yoman_status"] == "C" else "",
                    "date_get_cansel_limit": char12(trade_day + timedelta(days=2)) if deal["yoman_status"] == "C" else "",
                    "time_get_cansel_limit": "141500" if deal["yoman_status"] == "C" else "",
                    "shem_modia_status_not_catch": "OPS" if deal["yoman_status"] == "E" else "",
                    "date_status_not_catch": char12(trade_day + timedelta(days=3)) if deal["yoman_status"] == "E" else "",
                    "shaha_status_not_catch": "101500" if deal["yoman_status"] == "E" else "",
                    "first_date_modify": trade_char,
                    "first_time_modify": char6_clock(trade_time),
                    "last_date_modify": char12(trade_day + timedelta(days=1)),
                    "BankDiler": bank_name(deal["bank_id"])[:6],
                    "shem_mevatzea": "SHW1",
                    "earot": f"Limit status {deal['yoman_status']} for deal {deal['deal_id']}.",
                    "mispar_iska": deal["deal_id"],
                    "status_yoman": "A" if deal["yoman_status"] == "F" else "O",
                    "YomanNumber": yoman_line,
                    "PricoDiler": 401,
                    "disruption": deal["disruption"],
                    "disruption_type": 2 if deal["disruption"] else 0,
                    "disruption_rate": round(abs(delta), 4) if deal["disruption"] else 0,
                    "disruption_date": char8(trade_day) if deal["disruption"] else "",
                    "disruption_time": "114500" if deal["disruption"] else "",
                    "disruption_user_id": 9002 if deal["disruption"] else 0,
                },
            )
        )
        yoman_line += 1

        if deal["has_customer_confirmation"] or deal["has_bank_confirmation"]:
            snapshot["dbo.DealsConfirmations"].append(
                make_row(
                    "dbo.DealsConfirmations",
                    {
                        "DealID": deal["deal_id"],
                        "CustomerConfirmationContact": "Treasury Team" if deal["has_customer_confirmation"] else "",
                        "CustomerConfirmationDate": confirmation_date if deal["has_customer_confirmation"] else "",
                        "CustomerConfirmationTime": "101500" if deal["has_customer_confirmation"] else "",
                        "BankConfirmationContact": "Bank Ops" if deal["has_bank_confirmation"] else "",
                        "BankConfirmationDate": confirmation_date if deal["has_bank_confirmation"] else "",
                        "BankConfirmationTime": "104500" if deal["has_bank_confirmation"] else "",
                    },
                )
            )

        for change_index in range(deal["change_count"]):
            serial = change_serial
            snapshot["dbo.DealChangesLogHeaders"].append(
                make_row(
                    "dbo.DealChangesLogHeaders",
                    {
                        "DealNumber": deal["deal_id"],
                        "ChangeSerial": serial,
                        "Date": char8(trade_day + timedelta(days=change_index + 1)),
                        "Time": "111000",
                        "ChangeReason": ["Limit update", "Customer repricing", "Hedge period revision"][change_index % 3],
                        "UserID": 9001 + change_index,
                    },
                )
            )
            changed_fields = [
                ("LastRate", deal["benchmark_rate"], deal["final_rate"]),
                ("hedgePeriod", int(char8(settlement_day - timedelta(days=7))), int(char8(settlement_day))),
            ]
            if change_index > 0:
                changed_fields.append(("Commission", round(deal["commission_amount"] * 0.92, 2), deal["commission_amount"]))
            for internal_serial, (field_name, before_value, after_value) in enumerate(changed_fields, start=1):
                snapshot["dbo.DealChangesLogLines"].append(
                    make_row(
                        "dbo.DealChangesLogLines",
                        {
                            "DealChangeSerial": serial,
                            "InternalSerial": internal_serial,
                            "FieldName": field_name,
                            "ValueBeforeChange": str(before_value),
                            "ValueAfterChange": str(after_value),
                            "CCSLineNumber": 0,
                        },
                    )
                )
            change_serial += 1

    for extra_index, client in enumerate(CLIENTS, start=1):
        extra_day = BENCHMARK_DATES[extra_index * 3]
        snapshot["prico.yoman"].append(
            make_row(
                "prico.yoman",
                {
                    "LineNumber": yoman_line,
                    "taharich_bitzua": iso_dt(extra_day, 15, 0),
                    "mispar_bank": client["bank_cycle"][0],
                    "mispar_lakoah": client["id"],
                    "matbea_lerehisha": client["base_currency"],
                    "kamut_rehisha": 180_000,
                    "matbea_mehira": 40,
                    "kamut_mehira": 620_000,
                    "spot_limit": benchmark_average(client["pair_cycle"][0], extra_index),
                    "LastRate": 0,
                    "Branch": str(client["branch"]),
                    "Acount": client["account"],
                    "status_limit": "E",
                    "end_limit": char12(extra_day + timedelta(days=5)),
                    "end_time_limit": "170000",
                    "limit_place": "D",
                    "get_limit": "SHOWCASE",
                    "expirity": iso_dt(extra_day + timedelta(days=5), 17, 0),
                    "DealKind": "Limit",
                    "FXNumber": 0,
                    "earot": "Expired unmatched limit row for operational exceptions demo.",
                    "mispar_iska": 0,
                    "status_yoman": "O",
                    "YomanNumber": yoman_line,
                    "PricoDiler": 401,
                },
            )
        )
        yoman_line += 1

    return snapshot


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    snapshot = build_snapshot()
    table_counts = {table: len(rows) for table, rows in snapshot.items()}
    manifest = {
        "snapshot_name": "prico_showcase_v2",
        "generated_from": "talmudpedia-standalone/scripts/generate_prico_artifact_snapshot.py",
        "generated_for": "artifact-backed PRICO demo tools with full-schema-aligned JSON rows",
        "notes": [
            "Rows are generated to mirror the SQL table form for the touched PRICO demo tables.",
            "This snapshot extends the original showcase with richer pricing, operational, and hedge-coverage scenarios.",
            "Current tools remain supported, and new tables are included for future tool artifacts.",
        ],
        "tables": table_counts,
    }
    write_json(JSON_ROOT / "snapshot_manifest.json", manifest)
    for table, rows in snapshot.items():
        write_json(JSON_ROOT / f"{table}.json", rows)
    print(f"Wrote expanded PRICO artifact snapshot to {ROOT}")
    print(json.dumps(table_counts, indent=2))


if __name__ == "__main__":
    main()
