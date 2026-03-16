"""
黄金配置 Agent — 主逻辑
─────────────────────────────────────────────────────────────────
功能：
  1. 每小时检查金价，跌破阈值即推送建仓信号到飞书
  2. 每 6 小时用 Claude 扫描重大市场事件，有事件即推送
  3. 每天 09:00 推送一份黄金日报

运行方式：
  python agent.py              # 前台运行
  nohup python agent.py &      # 后台运行
─────────────────────────────────────────────────────────────────
"""
import logging
import time

import schedule

from config import (
    FEISHU_WEBHOOK_URL,
    PRICE_THRESHOLD,
    PRICE_CHECK_INTERVAL,
    EVENT_CHECK_INTERVAL,
    DAILY_REPORT_TIME,
)
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

# ── 去重：相邻两次价格触发须相差 >10 USD 才重复推送 ─────────────────────────
_last_alert_price: float = None


def job_check_price() -> None:
    """检查金价，触发建仓提醒。"""
    global _last_alert_price

    log.info("── 价格检查 ──")
    pi = get_price_info()
    if pi is None:
        log.warning("价格获取失败，跳过本次检查")
        return

    usd = pi["usd_per_oz"]
    log.info("当前金价: $%.2f/oz  ¥%.2f/g", usd, pi["cny_per_gram"])

    if usd < PRICE_THRESHOLD:
        if _last_alert_price is None or abs(usd - _last_alert_price) > 10:
            log.info("触发建仓信号！%.2f < 阈值 %s", usd, PRICE_THRESHOLD)
            summary = get_summary()
            advice  = get_advice(pi, summary)
            ok = feishu_bot.notify_price_alert(pi, summary, advice)
            log.info("飞书推送: %s", "✓" if ok else "✗")
            _last_alert_price = usd
        else:
            log.info("价格仍低于阈值但与上次触发相差 ≤10 USD，跳过重复推送")
    else:
        _last_alert_price = None  # 价格回升后重置，下次跌破再触发


def job_check_events() -> None:
    """扫描重大市场事件。"""
    log.info("── 事件扫描 ──")
    pi = get_price_info()
    if pi is None:
        log.warning("价格获取失败，跳过事件分析")
        return

    event_data = analyze_events()
    if event_data.get("has_major_event"):
        log.info("发现重大事件，推送飞书通知")
        summary = get_summary()
        ok = feishu_bot.notify_major_event(pi, event_data, summary)
        log.info("飞书推送: %s", "✓" if ok else "✗")
    else:
        log.info("未发现重大事件")


def job_daily_report() -> None:
    """每日早报。"""
    log.info("── 每日报告 ──")
    pi = get_price_info()
    if pi is None:
        log.warning("价格获取失败，跳过日报")
        return
    summary = get_summary()
    advice  = get_advice(pi, summary)
    ok = feishu_bot.notify_daily_report(pi, summary, advice)
    log.info("飞书推送: %s", "✓" if ok else "✗")


def run() -> None:
    """Agent 入口。"""
    log.info("=== 黄金配置 Agent 启动 ===")
    log.info("  价格阈值:   $%s/oz", PRICE_THRESHOLD)
    log.info("  月度限额:   ¥2,000")
    log.info("  飞书 Webhook: %s", "已配置 ✓" if FEISHU_WEBHOOK_URL else "❌ 未配置，请检查 .env")

    if not FEISHU_WEBHOOK_URL:
        log.error("FEISHU_WEBHOOK_URL 为空，Agent 无法推送通知，已退出。")
        return

    init_db()

    # 立即执行一次
    job_check_price()
    job_check_events()

    # 注册定时任务
    schedule.every(PRICE_CHECK_INTERVAL).minutes.do(job_check_price)
    schedule.every(EVENT_CHECK_INTERVAL).minutes.do(job_check_events)
    schedule.every().day.at(DAILY_REPORT_TIME).do(job_daily_report)

    log.info(
        "定时任务已注册: 价格检查每 %d 分钟 / 事件扫描每 %d 分钟 / 日报 %s",
        PRICE_CHECK_INTERVAL, EVENT_CHECK_INTERVAL, DAILY_REPORT_TIME,
    )

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
