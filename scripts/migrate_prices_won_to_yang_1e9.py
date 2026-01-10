"""One-off migration: normalize transaction_price_yang using 1 won = 1,000,000,000 yang.

This project stores prices primarily as total yang for analytics. Older loads may have:
- stored total using 1 won = 100,000,000 yang, OR
- stored only the yang remainder.

This script recomputes total yang as:
  total_yang = transaction_price_won * 1_000_000_000 + remainder

Remainder is inferred from the existing transaction_price_yang.

Safe to re-run: it only touches rows where the stored total is NULL or
smaller than won*1e9 (i.e., clearly not in the new scale).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure imports work regardless of current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import config
import psycopg2

WON_TO_YANG_NEW = 1_000_000_000
WON_TO_YANG_OLD = 100_000_000


def main() -> None:
    conn = psycopg2.connect(config.get_db_connection_string())
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE fact_market_transaction
        SET transaction_price_yang = (transaction_price_won * %(new)s) + (
            CASE
                WHEN transaction_price_yang IS NULL THEN 0
                WHEN transaction_price_yang BETWEEN 0 AND (%(old)s - 1) THEN transaction_price_yang
                ELSE GREATEST(0, transaction_price_yang - (transaction_price_won * %(old)s))
            END
        )
        WHERE transaction_price_won IS NOT NULL
          AND transaction_price_won > 0
          AND (
               transaction_price_yang IS NULL
               OR transaction_price_yang < (transaction_price_won * %(new)s)
          )
        """,
        {"new": WON_TO_YANG_NEW, "old": WON_TO_YANG_OLD},
    )
    updated = cur.rowcount
    conn.commit()

    cur.execute(
        """
        SELECT
          COUNT(*) AS rows,
          MIN(transaction_price_yang) AS min_total,
          MAX(transaction_price_yang) AS max_total,
          SUM(CASE WHEN transaction_price_yang < (transaction_price_won * %(new)s) THEN 1 ELSE 0 END) AS still_lt,
          SUM(CASE WHEN transaction_price_yang >= (transaction_price_won * %(new)s) THEN 1 ELSE 0 END) AS ok_ge
        FROM fact_market_transaction
        WHERE transaction_price_won > 0
        """,
        {"new": WON_TO_YANG_NEW},
    )
    check = cur.fetchone()

    cur.close()
    conn.close()

    print({"updated": updated, "check": check})


if __name__ == "__main__":
    main()
