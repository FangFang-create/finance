"""
黄金配置 Agent — 配置文件
所有可调参数集中于此，部署前先填写 .env 文件。
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── 投资参数 ─────────────────────────────────────────────────────────────────
TOTAL_BUDGET        = 500_000   # 总资产（人民币）
GOLD_ALLOC_PCT      = 0.12      # 黄金目标配置比例 12%  → ¥60,000
GOLD_BUDGET         = int(TOTAL_BUDGET * GOLD_ALLOC_PCT)   # ¥60,000

# 触发建仓的金价阈值
# 单位：人民币 / 克
PRICE_THRESHOLD     = 900       # CNY/g  —— 低于此价格触发建仓提醒
PRICE_UNIT          = "cny_per_gram"

MONTHLY_LIMIT       = 2_000     # 每月最大建仓金额（人民币）

# ── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
FEISHU_WEBHOOK_URL  = os.getenv("FEISHU_WEBHOOK_URL", "")

# ── 推送时间 ─────────────────────────────────────────────────────────────────
DAILY_REPORT_TIME   = "10:00"  # 每日推送时间（HH:MM，24 小时制）

# ── 汇率（用于 USD→CNY 换算，生产环境建议接实时汇率 API）────────────────────
USD_CNY_RATE = 7.2
TROY_OZ_TO_GRAM = 31.1035
