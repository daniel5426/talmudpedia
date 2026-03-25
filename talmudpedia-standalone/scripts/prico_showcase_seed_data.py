from __future__ import annotations

CLIENTS = [
    {"id": 32001, "name": "Orion Foods"},
    {"id": 32002, "name": "Atlas Medical"},
    {"id": 32003, "name": "Cedar Mobility"},
]

BANKS = [
    {"mispar_bank": 2, "bank": 2, "teur_bank": "Discount", "Teur_English": "Discount Bank", "fax": "", "mail": "", "swipt": "DSCTILIT", "derug": "A", "BlumbergID": "DSCT"},
    {"mispar_bank": 11, "bank": 11, "teur_bank": "Leumi", "Teur_English": "Bank Leumi", "fax": "", "mail": "", "swipt": "LUMIILIT", "derug": "A", "BlumbergID": "LUMI"},
    {"mispar_bank": 26, "bank": 26, "teur_bank": "Hapoalim", "Teur_English": "Bank Hapoalim", "fax": "", "mail": "", "swipt": "POALILIT", "derug": "A", "BlumbergID": "POLI"},
    {"mispar_bank": 34, "bank": 34, "teur_bank": "Mizrahi", "Teur_English": "Mizrahi Tefahot", "fax": "", "mail": "", "swipt": "MIZBILIT", "derug": "A", "BlumbergID": "MZTF"},
]

CURRENCIES = [
    {"mispar_matbea": 1, "teur_matbea": "USD", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "USD", "Curr_Heb_Name": "US Dollar", "CurrSign": "$", "HashCurrencyID": "USD"},
    {"mispar_matbea": 5, "teur_matbea": "GBP", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "GBP", "Curr_Heb_Name": "Pound", "CurrSign": "GBP", "HashCurrencyID": "GBP"},
    {"mispar_matbea": 6, "teur_matbea": "EUR", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "EUR", "Curr_Heb_Name": "Euro", "CurrSign": "EUR", "HashCurrencyID": "EUR"},
    {"mispar_matbea": 40, "teur_matbea": "ILS", "mekademhalukalepips": 10000, "rel": 1, "BankIsraelID": "ILS", "Curr_Heb_Name": "Shekel", "CurrSign": "ILS", "HashCurrencyID": "ILS"},
]

DEALS = [
    {"deal_id": 299101, "client_id": 32001, "bank_id": 26, "date": "20260210", "product_code": 6, "spot": 3.5510, "swap": 0.0030, "final_rate": 3.5540, "commission_rate": 0.03, "commission_amount": 750.0, "currency_1": 1, "currency_2": 40, "paku_date": "2026-02-10 09:10:00"},
    {"deal_id": 299102, "client_id": 32001, "bank_id": 2, "date": "20260211", "product_code": 8, "spot": 3.5670, "swap": 0.0, "final_rate": 3.5810, "commission_rate": 0.05, "commission_amount": 1800.0, "currency_1": 1, "currency_2": 40, "paku_date": "2026-02-11 10:00:00"},
    {"deal_id": 299103, "client_id": 32001, "bank_id": 11, "date": "20260212", "product_code": 4, "spot": 3.5980, "swap": 0.0110, "final_rate": 3.6090, "commission_rate": 0.03, "commission_amount": 1050.0, "currency_1": 1, "currency_2": 40, "paku_date": "2026-02-12 11:20:00"},
    {"deal_id": 299104, "client_id": 32001, "bank_id": 26, "date": "20260213", "product_code": 18, "spot": 3.5230, "swap": 0.0, "final_rate": 3.5310, "commission_rate": 0.05, "commission_amount": 1650.0, "currency_1": 1, "currency_2": 40, "paku_date": "2026-02-13 09:40:00"},
    {"deal_id": 299105, "client_id": 32001, "bank_id": 2, "date": "20260213", "product_code": 6, "spot": 3.5410, "swap": 0.0020, "final_rate": 3.5430, "commission_rate": 0.03, "commission_amount": 660.0, "currency_1": 1, "currency_2": 40, "paku_date": "2026-02-13 12:05:00"},
    {"deal_id": 299201, "client_id": 32002, "bank_id": 11, "date": "20260210", "product_code": 4, "spot": 4.0810, "swap": 0.0160, "final_rate": 4.0970, "commission_rate": 0.03, "commission_amount": 960.0, "currency_1": 6, "currency_2": 40, "paku_date": "2026-02-10 14:15:00"},
    {"deal_id": 299202, "client_id": 32002, "bank_id": 34, "date": "20260211", "product_code": 6, "spot": 4.0860, "swap": 0.0020, "final_rate": 4.0880, "commission_rate": 0.03, "commission_amount": 540.0, "currency_1": 6, "currency_2": 40, "paku_date": "2026-02-11 08:45:00"},
    {"deal_id": 299203, "client_id": 32002, "bank_id": 2, "date": "20260212", "product_code": 8, "spot": 4.1180, "swap": 0.0, "final_rate": 4.1320, "commission_rate": 0.05, "commission_amount": 1750.0, "currency_1": 6, "currency_2": 40, "paku_date": "2026-02-12 10:35:00"},
    {"deal_id": 299204, "client_id": 32002, "bank_id": 11, "date": "20260213", "product_code": 18, "spot": 4.1120, "swap": 0.0, "final_rate": 4.1210, "commission_rate": 0.05, "commission_amount": 1625.0, "currency_1": 6, "currency_2": 40, "paku_date": "2026-02-13 11:00:00"},
    {"deal_id": 299205, "client_id": 32002, "bank_id": 26, "date": "20260213", "product_code": 4, "spot": 4.0890, "swap": 0.0090, "final_rate": 4.0980, "commission_rate": 0.03, "commission_amount": 840.0, "currency_1": 6, "currency_2": 40, "paku_date": "2026-02-13 15:25:00"},
    {"deal_id": 299301, "client_id": 32003, "bank_id": 2, "date": "20260210", "product_code": 4, "spot": 4.8010, "swap": 0.0120, "final_rate": 4.8130, "commission_rate": 0.03, "commission_amount": 990.0, "currency_1": 5, "currency_2": 40, "paku_date": "2026-02-10 13:05:00"},
    {"deal_id": 299302, "client_id": 32003, "bank_id": 26, "date": "20260211", "product_code": 8, "spot": 4.8290, "swap": 0.0, "final_rate": 4.8420, "commission_rate": 0.05, "commission_amount": 1875.0, "currency_1": 5, "currency_2": 40, "paku_date": "2026-02-11 09:25:00"},
    {"deal_id": 299303, "client_id": 32003, "bank_id": 11, "date": "20260212", "product_code": 6, "spot": 4.7880, "swap": 0.0030, "final_rate": 4.7910, "commission_rate": 0.03, "commission_amount": 720.0, "currency_1": 5, "currency_2": 40, "paku_date": "2026-02-12 12:10:00"},
    {"deal_id": 299304, "client_id": 32003, "bank_id": 34, "date": "20260213", "product_code": 18, "spot": 4.8160, "swap": 0.0, "final_rate": 4.8280, "commission_rate": 0.05, "commission_amount": 1950.0, "currency_1": 5, "currency_2": 40, "paku_date": "2026-02-13 16:40:00"},
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

SSARS = [
    {"iska": 299103, "saar": 0.0, "dates": "1901-01-01 00:00:00", "times": "000000", "mevats": "SHOWCASE", "CloseDeal": 0},
    {"iska": 299203, "saar": 0.0, "dates": "1901-01-01 00:00:00", "times": "000000", "mevats": "SHOWCASE", "CloseDeal": 0},
    {"iska": 299302, "saar": 0.0, "dates": "1901-01-01 00:00:00", "times": "000000", "mevats": "SHOWCASE", "CloseDeal": 0},
]
