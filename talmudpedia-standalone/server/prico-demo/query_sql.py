import json
import os
import sys
from decimal import Decimal
from datetime import date, datetime

import pymssql


def serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def main():
    if len(sys.argv) < 2:
        raise SystemExit("SQL query argument is required")

    query = sys.argv[1]
    connection = pymssql.connect(
        server=f"{os.environ['PRICO_DB_HOST']}:{os.environ['PRICO_DB_PORT']}",
        user=os.environ["PRICO_DB_USER"],
        password=os.environ["PRICO_DB_PASSWORD"],
        database=os.environ["PRICO_DB_DATABASE"],
        as_dict=True,
        charset="UTF-8",
    )

    try:
        with connection.cursor(as_dict=True) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
    finally:
        connection.close()

    normalized_rows = []
    for row in rows:
        normalized_rows.append(
            {key: serialize_value(value) for key, value in row.items()}
        )

    sys.stdout.write(json.dumps(normalized_rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
