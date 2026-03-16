"""
多轮对话模块
用 Claude tool_runner 实现：Claude 自主决定调用哪些工具、调用几次，
最终返回给用户一条文本回复。

支持的工具：
  get_gold_price()         — 查实时金价
  get_investment_summary() — 查账户/仓位摘要
  analyze_market()         — 分析重大市场事件
  record_investment()      — 记录一笔建仓
"""
import logging
from collections import defaultdict

import anthropic
from anthropic import beta_tool

from config import ANTHROPIC_API_KEY
from gold_price import get_price_info
from investment_tracker import get_summary, add_investment
from analyzer import analyze_events

log = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM = """你是专业的黄金投资助手，服务于一位总资产 50 万的个人投资者。
投资参数：黄金目标仓位 12%（约 ¥60,000），每月建仓上限 ¥2,000，建仓阈值 ¥900/g。

你可以调用工具获取实时数据，回答用户关于金价、仓位、市场事件的问题，
并给出具体、可操作的建议。回复简洁，不超过 200 字。"""

# ── 工具定义 ─────────────────────────────────────────────────────────────────

@beta_tool
def get_gold_price() -> dict:
    """获取当前黄金实时价格，包含美元/盎司和人民币/克两种报价。"""
    result = get_price_info()
    return result if result else {"error": "价格获取失败，请稍后重试"}


@beta_tool
def get_investment_summary() -> dict:
    """获取投资账户摘要：总预算、黄金仓位进度、本月已建仓金额及剩余额度。"""
    return get_summary()


@beta_tool
def analyze_market() -> dict:
    """分析当前重大市场事件（美联储政策、地缘风险、通胀数据等），返回事件列表和市场情绪。"""
    return analyze_events()


@beta_tool
def record_investment(amount: float, note: str = "") -> str:
    """
    记录一笔黄金建仓。

    Args:
        amount: 建仓金额（人民币元），如 500.0
        note:   备注，如"黄金ETF 159937"
    """
    summary = get_summary()
    if amount <= 0:
        return "金额必须大于 0"
    if amount > summary["monthly_remaining"]:
        return f"超出本月剩余额度 ¥{summary['monthly_remaining']:.0f}，无法记录"
    pi = get_price_info()
    add_investment(
        amount=amount,
        price_usd=pi["usd_per_oz"] if pi else None,
        price_cny=pi["cny_per_gram"] if pi else None,
        note=note,
    )
    return f"已记录建仓 ¥{amount:.0f}，本月剩余额度 ¥{summary['monthly_remaining'] - amount:.0f}"


_TOOLS = [get_gold_price, get_investment_summary, analyze_market, record_investment]

# ── 对话历史（内存，按 open_id 隔离）────────────────────────────────────────
# 只存 user / assistant 文本轮次，工具调用细节在 tool_runner 内部处理
_MAX_HISTORY = 20   # 最多保留 20 轮（40 条消息）

_histories: dict[str, list] = defaultdict(list)


def chat(open_id: str, user_text: str) -> str:
    """
    处理一条用户消息，返回助手回复文本。
    内部用 tool_runner 让 Claude 自主决定是否/何时调用工具。
    """
    history = _histories[open_id]
    history.append({"role": "user", "content": user_text})

    try:
        runner = _client.beta.messages.tool_runner(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=SYSTEM,
            tools=_TOOLS,
            messages=history,
        )

        reply = ""
        for msg in runner:
            # 每次迭代是一个 BetaMessage；取最后出现的文本块作为最终回复
            text = next(
                (b.text for b in msg.content if getattr(b, "type", "") == "text"),
                "",
            )
            if text:
                reply = text

    except Exception as exc:
        log.error("chat 异常 open_id=%s: %s", open_id, exc)
        reply = "抱歉，处理请求时出现错误，请稍后再试。"

    if reply:
        history.append({"role": "assistant", "content": reply})

    # 超长时裁剪（保留最后 N 轮）
    if len(history) > _MAX_HISTORY * 2:
        _histories[open_id] = history[-(  _MAX_HISTORY * 2):]

    return reply or "抱歉，暂时无法回复。"
