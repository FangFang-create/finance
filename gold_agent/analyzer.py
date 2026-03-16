"""
Claude AI 分析模块
- analyze_events()      : 扫描重大市场事件
- get_advice()          : 根据当前行情给出具体建仓建议
"""
import json
import logging
from typing import Optional

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    PRICE_THRESHOLD,
    MONTHLY_LIMIT,
    GOLD_BUDGET,
    TOTAL_BUDGET,
)

log = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-opus-4-6"

# ── Prompts ──────────────────────────────────────────────────────────────────

_EVENT_SYSTEM = """你是专业的黄金市场分析师，擅长识别对黄金价格有重大影响的宏观事件。
请聚焦以下六类事件：
1. 美联储货币政策（加息/降息预期、点阵图、会议纪要）
2. 地缘政治风险（战争、制裁、主权债务危机）
3. 全球经济衰退信号（PMI、失业率、GDP 数据）
4. 央行购金 / 抛金（规模 ≥ 10 吨以上的公告）
5. 美元指数异常波动（单日 ±1% 以上）
6. 通胀数据超预期（CPI、PCE 偏离市场预期 ±0.3pp 以上）
只在有真实、近期的重大事件时设 has_major_event=true，不要捏造事件。"""

_EVENT_USER = """请分析当前（今日）是否存在上述六类重大事件，并以如下 JSON 格式回复（不要输出 JSON 以外的内容）：
{
  "has_major_event": true | false,
  "events": [
    {
      "type": "事件类型（如：美联储政策、地缘风险…）",
      "description": "具体描述（50 字内）",
      "impact": "positive | negative | neutral",
      "impact_level": "high | medium | low",
      "recommendation": "操作建议（30 字内）"
    }
  ],
  "overall_sentiment": "bullish | bearish | neutral",
  "summary": "综合分析（100 字内）"
}"""

_ADVICE_TMPL = """你是专业的黄金投资顾问，请根据以下信息给出简明建仓建议：

【当前行情】
- 金价（美元/盎司）：{usd_oz}
- 金价（人民币/克）：{cny_g}
- 建仓触发阈值：{threshold} USD/oz（当前价格{"已低于" if below else "高于"}阈值）

【投资者参数】
- 总资产：¥{total_budget:,}
- 黄金目标仓位：12%（¥{gold_budget:,}）
- 已累计建仓：¥{total_invested:,}
- 黄金剩余预算：¥{gold_remaining:,}
- 本月已建仓：¥{monthly_spent:,}
- 本月剩余额度：¥{monthly_remaining:,}（上限 ¥{monthly_limit:,}）

请给出不超过 120 字的建议，包含：
① 是否建议本次建仓  ② 建议金额（不超过本月剩余额度）  ③ 推荐工具（优先黄金 ETF）"""


# ── 公共函数 ──────────────────────────────────────────────────────────────────

def analyze_events() -> dict:
    """调用 Claude 分析当日重大市场事件，返回结构化字典。"""
    try:
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=_EVENT_SYSTEM,
            messages=[{"role": "user", "content": _EVENT_USER}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except Exception as exc:
        log.error("事件分析失败: %s", exc)
    return {"has_major_event": False, "events": [], "summary": "分析服务暂时不可用"}


def get_advice(price_info: dict, summary: dict) -> str:
    """根据行情和账户状态，调用 Claude 生成建仓建议文字。"""
    usd_oz = price_info.get("usd_per_oz", 0)
    cny_g  = price_info.get("cny_per_gram", 0)
    below  = usd_oz < PRICE_THRESHOLD
    prompt = _ADVICE_TMPL.format(
        usd_oz=f"{usd_oz:.2f}",
        cny_g=f"{cny_g:.2f}",
        threshold=PRICE_THRESHOLD,
        below=below,
        total_budget=summary["total_budget"],
        gold_budget=summary["gold_budget"],
        total_invested=summary["total_invested"],
        gold_remaining=summary["gold_remaining"],
        monthly_spent=summary["monthly_spent"],
        monthly_remaining=summary["monthly_remaining"],
        monthly_limit=summary["monthly_limit"],
    )
    try:
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=256,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )
        return next((b.text for b in resp.content if b.type == "text"), "建议获取失败")
    except Exception as exc:
        log.error("建议生成失败: %s", exc)
        return f"建议获取失败: {exc}"
