"""
飞书应用机器人客户端
负责：获取 tenant_access_token、发送消息

与 feishu_bot.py 的区别：
  feishu_bot.py  — 自定义机器人 Webhook，只能单向推送
  feishu_app.py  — 应用机器人 API，可双向收发消息
"""
import json
import logging
import os
import threading
import time

import requests

log = logging.getLogger(__name__)

FEISHU_APP_ID     = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

_BASE = "https://open.feishu.cn/open-apis"

# ── Token 缓存（线程安全）────────────────────────────────────────────────────
_cache = {"token": "", "expires_at": 0.0}
_lock  = threading.Lock()


def get_access_token() -> str:
    with _lock:
        if time.time() < _cache["expires_at"] - 60:
            return _cache["token"]
        resp = requests.post(
            f"{_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 token 失败: {data}")
        _cache["token"]      = data["tenant_access_token"]
        _cache["expires_at"] = time.time() + data.get("expire", 7200)
        log.debug("token 已刷新，有效期 %ds", data.get("expire", 7200))
        return _cache["token"]


# ── 发送文本消息 ─────────────────────────────────────────────────────────────
def send_text(open_id: str, text: str) -> bool:
    """向指定用户发送文本消息。"""
    try:
        token = get_access_token()
        resp = requests.post(
            f"{_BASE}/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=json.dumps({
                "receive_id": open_id,
                "msg_type":   "text",
                "content":    json.dumps({"text": text}),
            }, ensure_ascii=False),
            timeout=10,
        )
        result = resp.json()
        if result.get("code") != 0:
            log.warning("消息发送失败: %s", result)
            return False
        return True
    except Exception as exc:
        log.error("send_text 异常: %s", exc)
        return False
