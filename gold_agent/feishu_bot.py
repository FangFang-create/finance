"""
飞书自定义机器人推送模块
使用飞书「自定义机器人」Webhook（消息卡片格式）。

配置步骤：
1. 飞书群 → 设置 → 机器人 → 添加自定义机器人
2. 复制 Webhook 地址，填入 .env 的 FEISHU_WEBHOOK_URL
3. 如启用了「签名校验」，同时填入 FEISHU_SECRET

文档：https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
"""
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Optional

import requests

from config import FEISHU_WEBHOOK_URL

log = logging.getLogger(__name__)
FEISHU_SECRET: Optional[str] = os.getenv("FEISHU_SECRET")


# ── 签名（可选）─────────────────────────────────────────────────────────────
import base64
import hmac as _hmac


def _make_sign(timestamp: str) -> str:
    """飞书机器人签名校验（开启后必须携带，否则请求会被拒绝）。"""
    string_to_sign = f"{timestamp}\n{FEISHU_SECRET}"
    hmac_code = _hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    )
    return base64.b64encode(hmac_code.digest()).decode("utf-8")


# ── 发送卡片 ─────────────────────────────────────────────────────────────────
def _post(card: dict) -> bool:
    payload: dict = {"msg_type": "interactive", "card": card}
    if FEISHU_SECRET:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = _make_sign(ts)
    try:
        resp = requests.post(
            FEISHU_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False),
            timeout=10,
        )
        result = resp.json()
        if result.get("code", 0) != 0:
            log.warning("飞书推送非零响应: %s", result)
            return False
        return True
    except Exception as exc:
        log.error("飞书推送异常: %s", exc)
        return False


# ── 卡片构建辅助 ─────────────────────────────────────────────────────────────
_IMPACT_COLOR = {"positive": "green", "negative": "red", "neutral": "grey"}
_IMPACT_ICON  = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}


def _price_fields(pi: dict) -> list:
    return [
        {
            "tag": "column_set",
            "flex_mode": "stretch",
            "columns": [
                {
                    "tag": "column", "width": "weighted", "weight": 1,
                    "elements": [{"tag": "div", "text": {
                        "tag": "lark_md",
                        "content": f"**💰 金价（USD/oz）**\n`${pi['usd_per_oz']:.2f}`",
                    }}],
                },
                {
                    "tag": "column", "width": "weighted", "weight": 1,
                    "elements": [{"tag": "div", "text": {
                        "tag": "lark_md",
                        "content": f"**💴 金价（CNY/g）**\n`¥{pi['cny_per_gram']:.2f}`",
                    }}],
                },
            ],
        },
        {"tag": "hr"},
    ]


def _investment_fields(s: dict) -> list:
    pct = s["total_invested"] / s["gold_budget"] * 100 if s["gold_budget"] else 0
    return [
        {
            "tag": "column_set",
            "flex_mode": "stretch",
            "columns": [
                {
                    "tag": "column", "width": "weighted", "weight": 1,
                    "elements": [{"tag": "div", "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**本月已建仓**\n`¥{s['monthly_spent']:,.0f}`\n"
                            f"剩余额度 `¥{s['monthly_remaining']:,.0f}`"
                        ),
                    }}],
                },
                {
                    "tag": "column", "width": "weighted", "weight": 1,
                    "elements": [{"tag": "div", "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**累计建仓**\n`¥{s['total_invested']:,.0f}`\n"
                            f"黄金预算进度 `{pct:.1f}%`"
                        ),
                    }}],
                },
            ],
        },
        {"tag": "hr"},
    ]


def _advice_element(advice: str) -> list:
    return [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🤖 AI 建议**\n{advice}"},
        },
        {"tag": "hr"},
    ]


def _event_elements(events: list) -> list:
    elems = []
    for ev in events:
        icon = _IMPACT_ICON.get(ev.get("impact", "neutral"), "⚪")
        elems.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"{icon} **{ev.get('type', '')}** "
                    f"[{ev.get('impact_level', '')}]\n"
                    f"{ev.get('description', '')}\n"
                    f"> 建议：{ev.get('recommendation', '')}"
                ),
            },
        })
    return elems


def _timestamp_note() -> dict:
    return {
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"更新于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        ],
    }


def _build_card(title: str, color: str, elements: list) -> dict:
    return {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": elements + [_timestamp_note()],
    }


# ── 对外接口 ─────────────────────────────────────────────────────────────────

def notify_price_alert(price_info: dict, summary: dict, advice: str) -> bool:
    """金价跌破阈值 → 建仓信号"""
    elements = (
        _price_fields(price_info)
        + _investment_fields(summary)
        + _advice_element(advice)
    )
    card = _build_card(
        title=f"🚨 黄金建仓信号 ｜ ${price_info['usd_per_oz']:.0f}/oz",
        color="red",
        elements=elements,
    )
    return _post(card)


def notify_major_event(price_info: dict, event_data: dict, summary: dict) -> bool:
    """重大市场事件推送"""
    sentiment_map = {"bullish": "📈 看多", "bearish": "📉 看空", "neutral": "➡️ 中性"}
    sentiment = sentiment_map.get(event_data.get("overall_sentiment", "neutral"), "")
    elements = (
        _price_fields(price_info)
        + _investment_fields(summary)
        + _event_elements(event_data.get("events", []))
        + [{"tag": "hr"}]
        + _advice_element(event_data.get("summary", ""))
    )
    card = _build_card(
        title=f"⚡ 黄金市场重大事件 ｜ {sentiment}",
        color="orange",
        elements=elements,
    )
    return _post(card)


def notify_daily_report(price_info: dict, summary: dict, advice: str) -> bool:
    """每日早报"""
    elements = (
        _price_fields(price_info)
        + _investment_fields(summary)
        + _advice_element(advice)
    )
    card = _build_card(
        title=f"📊 黄金日报 ｜ {datetime.now().strftime('%Y-%m-%d')}",
        color="blue",
        elements=elements,
    )
    return _post(card)
