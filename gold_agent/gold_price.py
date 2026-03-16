"""
黄金价格获取模块
主数据源：yfinance  GC=F（COMEX 黄金期货，美元/盎司）
备用数据源：metals.live 免费 API
"""
import logging
from datetime import datetime
from typing import Optional

import requests

from config import USD_CNY_RATE, TROY_OZ_TO_GRAM

log = logging.getLogger(__name__)


def _fetch_yfinance() -> Optional[float]:
    try:
        import yfinance as yf
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d")
        if not df.empty:
            price = float(df["Close"].iloc[-1])
            log.debug("yfinance GC=F: %.2f", price)
            return price
    except Exception as exc:
        log.warning("yfinance 获取失败: %s", exc)
    return None


def _fetch_metals_live() -> Optional[float]:
    try:
        resp = requests.get(
            "https://api.metals.live/v1/spot/gold",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            price = float(data[0].get("price", 0))
            log.debug("metals.live: %.2f", price)
            return price
    except Exception as exc:
        log.warning("metals.live 获取失败: %s", exc)
    return None


def get_gold_price_usd() -> Optional[float]:
    """返回黄金现货价格（美元 / 盎司），失败返回 None。"""
    return _fetch_yfinance() or _fetch_metals_live()


def usd_oz_to_cny_gram(usd_oz: float, rate: float = USD_CNY_RATE) -> float:
    """美元/盎司 → 人民币/克"""
    return round(usd_oz * rate / TROY_OZ_TO_GRAM, 2)


def get_price_info() -> Optional[dict]:
    """
    返回完整价格信息字典：
    {
        "usd_per_oz":   float,
        "cny_per_gram": float,
        "timestamp":    str   (ISO 8601)
    }
    """
    usd = get_gold_price_usd()
    if usd is None:
        return None
    return {
        "usd_per_oz":   round(usd, 2),
        "cny_per_gram": usd_oz_to_cny_gram(usd),
        "timestamp":    datetime.now().isoformat(),
    }
