"""
FastAPI 服务入口
─────────────────────────────────────────────────────────────────
同时承担两个职责：
  1. POST /webhook  — 接收飞书事件（用户消息），调用 conversation.chat() 回复
  2. 后台线程        — 每天 10:00 执行定时推送（复用 agent.job_daily）

启动方式：
  uvicorn server:app --host 0.0.0.0 --port 8000

飞书后台配置：
  事件订阅 → 请求地址填 https://<你的域名>/webhook
  订阅事件：im.message.receive_v1（接收消息）
─────────────────────────────────────────────────────────────────
"""
import json
import logging
import os
import re
import threading
import time

import schedule
import uvicorn
from fastapi import FastAPI, Request

from agent import job_daily
from config import DAILY_REPORT_TIME
from conversation import chat
from feishu_app import send_text
from investment_tracker import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("server")

app = FastAPI(title="黄金配置 Agent")

# ── 事件去重（防止飞书重试导致重复处理）────────────────────────────────────
_seen_events: set[str] = set()
_SEEN_MAX = 1000


# ── Webhook 路由 ─────────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    # 1. URL 验证（首次配置时飞书发送 challenge）
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    # 2. 解析事件
    header     = body.get("header", {})
    event_type = header.get("event_type", "")
    event_id   = header.get("event_id", "")

    # 去重
    if event_id in _seen_events:
        return {"ok": True}
    _seen_events.add(event_id)
    if len(_seen_events) > _SEEN_MAX:
        _seen_events.clear()

    if event_type != "im.message.receive_v1":
        return {"ok": True}

    event = body.get("event", {})
    msg   = event.get("message", {})

    # 只处理文本消息
    if msg.get("message_type") != "text":
        return {"ok": True}

    content   = json.loads(msg.get("content", "{}"))
    user_text = content.get("text", "").strip()

    # 去掉 @机器人 前缀（群聊场景）
    user_text = re.sub(r"@\S+\s*", "", user_text).strip()
    if not user_text:
        return {"ok": True}

    open_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
    if not open_id:
        return {"ok": True}

    log.info("收到消息 open_id=%s: %s", open_id, user_text[:50])

    # 异步处理（避免超过飞书 3s 响应超时）
    threading.Thread(
        target=_handle_message,
        args=(open_id, user_text),
        daemon=True,
    ).start()

    return {"ok": True}


def _handle_message(open_id: str, user_text: str) -> None:
    reply = chat(open_id, user_text)
    ok = send_text(open_id, reply)
    log.info("回复 open_id=%s: %s [%s]", open_id, reply[:50], "✓" if ok else "✗")


# ── 定时任务后台线程 ─────────────────────────────────────────────────────────

def _run_scheduler() -> None:
    schedule.every().day.at(DAILY_REPORT_TIME).do(job_daily)
    log.info("定时任务已注册，每日 %s 推送", DAILY_REPORT_TIME)
    while True:
        schedule.run_pending()
        time.sleep(30)


# ── 启动事件 ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()
    t = threading.Thread(target=_run_scheduler, daemon=True)
    t.start()
    log.info("=== 黄金配置 Agent 已启动 ===")


# ── 直接运行 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
