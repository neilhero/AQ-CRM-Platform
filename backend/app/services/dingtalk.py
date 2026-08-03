import json
import logging
import os
import threading
import time
from datetime import datetime
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)

_token_lock = threading.Lock()
_token_value = None
_token_expires_at = 0


class DingTalkError(RuntimeError):
    pass


def _get_crm_public_url():
    configured_url = os.getenv("CRM_PUBLIC_URL", "https://an-ai.cn").strip().rstrip("/")
    canonical_url = os.getenv("CRM_CANONICAL_URL", "https://an-ai.cn").strip().rstrip("/")
    try:
        if urlsplit(configured_url).hostname == "121.41.66.121":
            return canonical_url
    except ValueError:
        return canonical_url
    return configured_url or canonical_url


def _post_json(url, payload, headers=None, timeout=10):
    request_headers = {"Content-Type": "application/json; charset=utf-8"}
    request_headers.update(headers or {})
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_access_token():
    global _token_value, _token_expires_at

    now = time.time()
    if _token_value and now < _token_expires_at:
        return _token_value

    with _token_lock:
        now = time.time()
        if _token_value and now < _token_expires_at:
            return _token_value

        client_id = os.getenv("DINGTALK_CLIENT_ID", "").strip()
        client_secret = os.getenv("DINGTALK_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise DingTalkError("DingTalk client credentials are not configured")

        result = _post_json(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            {"appKey": client_id, "appSecret": client_secret},
        )
        token = result.get("accessToken")
        if not token:
            raise DingTalkError(result.get("message") or "DingTalk access token request failed")

        expires_in = int(result.get("expireIn") or 7200)
        _token_value = token
        _token_expires_at = now + max(expires_in - 300, 60)
        return token


def send_work_notification(dingtalk_userid, title, markdown_text, target_url):
    if os.getenv("DINGTALK_ENABLED", "").lower() not in {"1", "true", "yes", "on"}:
        return {"status": "skipped", "reason": "disabled"}
    if not dingtalk_userid:
        return {"status": "skipped", "reason": "user_not_bound"}

    agent_id = os.getenv("DINGTALK_AGENT_ID", "").strip()
    if not agent_id:
        raise DingTalkError("DINGTALK_AGENT_ID is not configured")

    token = _get_access_token()
    query = urlencode({"access_token": token})
    result = _post_json(
        "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?" + query,
        {
            "agent_id": int(agent_id) if agent_id.isdigit() else agent_id,
            "userid_list": dingtalk_userid,
            "to_all_user": False,
            "msg": {
                "msgtype": "action_card",
                "action_card": {
                    "title": title,
                    "markdown": markdown_text,
                    "single_title": "查看售前申请",
                    "single_url": target_url,
                },
            },
        },
        timeout=15,
    )
    if int(result.get("errcode") or 0) != 0:
        raise DingTalkError(result.get("errmsg") or "DingTalk work notification failed")
    return {"status": "sent", "task_id": result.get("task_id")}


def send_presales_notification_safe(
    dingtalk_userid,
    request_id,
    customer_name,
    opportunity_name,
    request_type,
    requester_name,
    scheduled_date,
    details,
    requester_dingtalk_userid=None,
):
    public_url = _get_crm_public_url()
    target_url = f"{public_url}/#/presales?request_id={request_id}"
    schedule_text = (
        scheduled_date.strftime("%Y-%m-%d %H:%M")
        if isinstance(scheduled_date, datetime)
        else str(scheduled_date or "未设置")
    )
    summary = (details or "").strip()
    if len(summary) > 180:
        summary = summary[:177] + "..."

    context_lines = [
        f"- 客户：{customer_name or '-'}",
        f"- 商机：{opportunity_name or '-'}",
        f"- 协同类型：{request_type or '-'}",
        f"- 申请人：{requester_name or '-'}",
        f"- 排期：{schedule_text}",
        f"- 需求：{summary or '-'}",
    ]
    notifications = [
        (
            dingtalk_userid,
            "安泉CRM：新的售前协同申请",
            "### 售前协同待处理",
            "presales",
        )
    ]
    if requester_dingtalk_userid and requester_dingtalk_userid != dingtalk_userid:
        notifications.append(
            (
                requester_dingtalk_userid,
                "安泉CRM：售前协同申请已提交",
                "### 售前协同已提交",
                "requester",
            )
        )

    for recipient_id, title, heading, audience in notifications:
        try:
            result = send_work_notification(
                recipient_id,
                title,
                "\n".join([heading, *context_lines]),
                target_url,
            )
            logger.info(
                "DingTalk presales notification result request_id=%s audience=%s status=%s",
                request_id,
                audience,
                result.get("status"),
            )
        except Exception:
            logger.exception(
                "DingTalk presales notification failed request_id=%s audience=%s",
                request_id,
                audience,
            )
