"""
投资记录追踪（SQLite）
记录每次建仓，提供月度/总计查询。
"""
import sqlite3
import logging
from datetime import date
from pathlib import Path

from config import MONTHLY_LIMIT, GOLD_BUDGET, TOTAL_BUDGET, GOLD_ALLOC_PCT

log = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent / "investment.db"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT    NOT NULL,
            amount        REAL    NOT NULL,
            price_usd     REAL,
            price_cny     REAL,
            note          TEXT,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    log.debug("DB 初始化完毕: %s", DB_PATH)


def add_investment(
    amount: float,
    price_usd: float = None,
    price_cny: float = None,
    note: str = "",
) -> None:
    """记录一笔建仓（手动调用，或将来接入自动化下单后回调）。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO investments (date, amount, price_usd, price_cny, note) VALUES (?,?,?,?,?)",
        (date.today().isoformat(), amount, price_usd, price_cny, note),
    )
    conn.commit()
    conn.close()


def _query_sum(where_clause: str, params: tuple) -> float:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(f"SELECT COALESCE(SUM(amount), 0) FROM investments WHERE {where_clause}", params)
    result = cur.fetchone()[0]
    conn.close()
    return float(result)


def get_monthly_spent(year: int = None, month: int = None) -> float:
    today = date.today()
    y, m = year or today.year, month or today.month
    return _query_sum("date LIKE ?", (f"{y}-{m:02d}%",))


def get_total_invested() -> float:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM investments")
    result = float(cur.fetchone()[0])
    conn.close()
    return result


def get_summary() -> dict:
    total     = get_total_invested()
    monthly   = get_monthly_spent()
    return {
        "total_budget":       TOTAL_BUDGET,
        "gold_budget":        GOLD_BUDGET,
        "gold_alloc_pct":     GOLD_ALLOC_PCT,
        "total_invested":     total,
        "gold_remaining":     max(0.0, GOLD_BUDGET - total),
        "monthly_limit":      MONTHLY_LIMIT,
        "monthly_spent":      monthly,
        "monthly_remaining":  max(0.0, MONTHLY_LIMIT - monthly),
    }
