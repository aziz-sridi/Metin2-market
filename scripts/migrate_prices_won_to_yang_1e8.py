"""One-off migration: normalize transaction_price_yang using 1 won = 100,000,000 yang.

If the warehouse currently contains totals computed with 1 won = 1,000,000,000 yang,
this script converts them back to the 1e8 scale while preserving the yang remainder.

Assumption: transaction_price_won stores the won component.
Remainder is inferred as:
  remainder = transaction_price_yang - transaction_price_won * 1_000_000_000
for rows that are clearly in the 1e9 scale.

Safe to re-run: it only touches rows where total >= won*1e9.
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

WON_TO_YANG_CANON = 100_000_000
WON_TO_YANG_OLD = 1_000_000_000


def main() -> None:
    conn = psycopg2.connect(config.get_db_connection_string())
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE fact_market_transaction
        SET transaction_price_yang = (transaction_price_won * %(canon)s) + GREATEST(
            0,
            transaction_price_yang - (transaction_price_won * %(old)s)
        )
        WHERE transaction_price_won IS NOT NULL
          AND transaction_price_won > 0
          AND transaction_price_yang >= (transaction_price_won * %(old)s)
        """,
        {"canon": WON_TO_YANG_CANON, "old": WON_TO_YANG_OLD},
    )
    updated = cur.rowcount
    conn.commit()

    cur.execute(
        """
        SELECT
          COUNT(*) AS rows,
          MIN(transaction_price_yang) AS min_total,
          MAX(transaction_price_yang) AS max_total,
          SUM(CASE WHEN transaction_price_yang >= (transaction_price_won * %(old)s) THEN 1 ELSE 0 END) AS still_oldscale,
          SUM(CASE WHEN transaction_price_yang < (transaction_price_won * %(old)s) THEN 1 ELSE 0 END) AS ok_not_oldscale
        FROM fact_market_transaction
        WHERE transaction_price_won > 0
        """,
        {"old": WON_TO_YANG_OLD},
    )
    check = cur.fetchone()

    cur.close()
    conn.close()

    print({"updated": updated, "check": check})


if __name__ == "__main__":
    main()
