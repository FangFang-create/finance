"""
黄金配置 Agent — 主逻辑
─────────────────────────────────────────────────────────────────
功能：每天 10:00 推送一条飞书消息，包含：
  - 当日金价 + 是否触达建仓阈值
  - Claude AI 重大事件扫描结果
  - 具体建仓建议

运行方式：
  python agent.py              # 前台运行
  nohup python agent.py &      # 后台运行
─────────────────────────────────────────────────────────────────
"""
import logging
import time

import schedule

from config import FEISHU_WEBHOOK_URL, PRICE_THRESHOLD, DAILY_REPORT_TIME
from gold_price import get_price_info
from investment_tracker import init_db, get_summary
from analyzer import analyze_events, get_advice
import feishu_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gold_agent")


def job_daily() -> None:
    """每日 10:00 执行：价格 + 事件 + 建议，合并为一条飞书消息。"""
    log.info("── 每日检查开始 ──")

    pi = get_price_info()
    if pi is None:
        log.warning("价格获取失败，跳过今日推送")
        return

    usd = pi["usd_per_oz"]
    log.info("当前金价: $%.2f/oz  ¥%.2f/g", usd, pi["cny_per_gram"])

    summary    = get_summary()
    event_data = analyze_events()
    advice     = get_advice(pi, summary)

    below_threshold = usd < PRICE_THRESHOLD

    if below_threshold:
        log.info("金价低于阈值 $%s，推送建仓信号", PRICE_THRESHOLD)
        ok = feishu_bot.notify_price_alert(pi, summary, advice)
    elif event_data.get("has_major_event"):
        log.info("发现重大市场事件，推送事件通知")
        ok = feishu_bot.notify_major_event(pi, event_data, summary)
    else:
        log.info("无触发信号，推送常规日报")
        ok = feishu_bot.notify_daily_report(pi, summary, advice)

    log.info("飞书推送: %s", "✓" if ok else "✗")


def run() -> None:
    """Agent 入口。"""
    log.info("=== 黄金配置 Agent 启动 ===")
    log.info("  推送时间:   每日 %s", DAILY_REPORT_TIME)
    log.info("  价格阈值:   $%s/oz", PRICE_THRESHOLD)
    log.info("  飞书 Webhook: %s", "已配置 ✓" if FEISHU_WEBHOOK_URL else "❌ 未配置，请检查 .env")

    if not FEISHU_WEBHOOK_URL:
        log.error("FEISHU_WEBHOOK_URL 为空，Agent 无法推送通知，已退出。")
        return

    init_db()
    schedule.every().day.at(DAILY_REPORT_TIME).do(job_daily)
    log.info("定时任务已注册，等待 %s 触发…", DAILY_REPORT_TIME)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
