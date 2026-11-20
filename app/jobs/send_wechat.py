"""Send pending notifications via WeChat template message (design §8).

``python -m app.jobs.send_wechat`` — run right after ``app.jobs.daily``
in the same cron. Picks up rows ``daily`` created with
``status='sent'`` and ``channel='in_app'`` and, for users who have
linked WeChat (``users.wechat_openid``), sends the matching template
message and flips the row to ``channel='wechat'``.

Required env (design §8, in ``/home/ubuntu/imsf-v2.env``):
``WECHAT_APPID``, ``WECHAT_SECRET``, ``WECHAT_TEMPLATE_LAZY_TRACKING``,
``WECHAT_TEMPLATE_MAINTENANCE``. If ANY of the four is missing/empty
the job prints a skip line and exits 0 — it never crashes the cron
for lack of WeChat config. This is the REQUIRED behaviour right now:
D2 credentials are NOT available yet (checked 2026-11-20 — no WeChat
config exists on Oregon), so the guard path is the only live path.

====================================================================
UNTESTED — SEND PATH: no D2 credentials exist to test against, so
everything below the config guard has never run against the real
WeChat API. Do not treat a successful guard run as proof the send
path works. When Lam supplies the Guiyan AppID/secret + template
IDs, re-verify the token call and one template send end to end.
The exact template data fields below are a best guess from the
payloads in design §6.2/§8 and MUST be confirmed against the
templates Lam registers — WeChat rejects a send whose data keys do
not match the registered template.
====================================================================

On send failure (non-zero errcode, HTTP/network error) the row is
marked ``status='failed'`` and the error is appended to
``payload_json.error``; the row is never deleted, so it can be
retried by hand (design §8). A failure in one notification never
stops the rest.
"""

import json
import logging
import os
import sys
import urllib.error
import urllib.request

from sqlalchemy import text

from app.config import settings
from app.db import get_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("imsf-v2-jobs-send-wechat")

TOKEN_URL = ("https://api.weixin.qq.com/cgi-bin/token"
             "?grant_type=client_credential&appid={appid}&secret={secret}")
SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"
HTTP_TIMEOUT_SECONDS = 15

REQUIRED_VARS = (
    "WECHAT_APPID",
    "WECHAT_SECRET",
    "WECHAT_TEMPLATE_LAZY_TRACKING",
    "WECHAT_TEMPLATE_MAINTENANCE",
)

# Env values are read here (not only via app.config.Settings) so the
# guard can name exactly which vars are missing.
ENV = {name: os.environ.get(name, "") for name in REQUIRED_VARS}


def _missing_vars() -> list[str]:
    return [name for name in REQUIRED_VARS if not ENV[name].strip()]


def _http_json(url: str, data: dict | None = None) -> dict:
    """GET (data=None) or POST JSON; returns the decoded JSON body."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") \
        if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_access_token() -> str:
    """Fetch an access_token, cached in memory for this run only."""
    resp = _http_json(TOKEN_URL.format(appid=ENV["WECHAT_APPID"],
                                       secret=ENV["WECHAT_SECRET"]))
    token = resp.get("access_token")
    if not token:
        raise RuntimeError(f"wechat token fetch failed: {resp!r}")
    return token


def _template_data(ntype: str, payload: dict) -> tuple[str, dict]:
    """(template_id, data) for a notification.

    Data keys are a best guess — see the UNTESTED note at the top of
    this file; confirm them against the registered templates.
    """
    if ntype == "lazy_tracking":
        template_id = settings.wechat_template_lazy_tracking
        data = {
            "first": {"value": f"Tủ lạnh còn {payload.get('item_name')} không?"},
            "keyword1": {"value": str(payload.get("item_name", ""))},
            "keyword2": {"value": str(payload.get("expiry_date", ""))},
            "remark": {"value": "Đã dùng hết / Còn, gia hạn thêm"},
        }
    else:  # maintenance_reminder
        template_id = settings.wechat_template_maintenance
        data = {
            "first": {"value": f"{payload.get('equipment_name')} đến hạn bảo trì"},
            "keyword1": {"value": str(payload.get("equipment_name", ""))},
            "keyword2": {"value": str(payload.get("next_maintenance_date", ""))},
            "remark": {"value": "Vui lòng mở app để xem chi tiết bảo trì"},
        }
    return template_id, data


def _mark_failed(conn, notif_id, error: str) -> None:
    conn.execute(
        text("UPDATE notifications SET status = 'failed',"
             " payload_json = COALESCE(payload_json, '{}'::jsonb)"
             " || jsonb_build_object('error', :err)"
             " WHERE id = :nid"),
        {"err": error[:1000], "nid": notif_id},
    )


def send_pending() -> dict:
    """Send all pending notifications. Returns the count dict."""
    counts = {"sent": 0, "failed": 0, "skipped_no_openid": 0}
    engine = get_engine()
    with engine.connect() as conn:
        pending = conn.execute(
            text("SELECT id, user_id, type, payload_json FROM notifications"
                 " WHERE status = 'sent' AND channel = 'in_app'"
                 " AND type IN ('lazy_tracking', 'maintenance_reminder')"
                 " ORDER BY sent_at")
        ).all()
    if not pending:
        return counts
    try:
        token = _get_access_token()
    except Exception as exc:  # noqa: BLE001 — token layer, not per-row
        log.error("wechat access_token fetch failed, %d notification(s)"
                  " left untouched for the next run: %s", len(pending), exc)
        return counts
    for notif_id, user_id, ntype, payload in pending:
        try:
            with engine.connect() as conn:
                openid = conn.execute(
                    text("SELECT wechat_openid FROM users WHERE id = :uid"),
                    {"uid": user_id},
                ).scalar_one_or_none()
            if not openid:
                log.info("notification=%s user=%s has no wechat_openid,"
                         " skipping", notif_id, user_id)
                counts["skipped_no_openid"] += 1
                continue
            template_id, data = _template_data(ntype, payload or {})
            resp = _http_json(
                f"{SEND_URL}?access_token={token}",
                {"touser": openid, "template_id": template_id, "data": data},
            )
            if resp.get("errcode") == 0:
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE notifications SET channel = 'wechat'"
                             " WHERE id = :nid"),
                        {"nid": notif_id},
                    )
                counts["sent"] += 1
                log.info("notification=%s sent via wechat (msgid=%s)",
                         notif_id, resp.get("msgid"))
            else:
                err = f"wechat send errcode={resp.get('errcode')} errmsg={resp.get('errmsg')}"
                with engine.begin() as conn:
                    _mark_failed(conn, notif_id, err)
                counts["failed"] += 1
                log.warning("notification=%s failed: %s", notif_id, err)
        except Exception as exc:  # noqa: BLE001 — per-notification, keep going
            log.error("notification=%s send error: %s", notif_id, exc)
            try:
                with engine.begin() as conn:
                    _mark_failed(conn, notif_id, f"{type(exc).__name__}: {exc}")
                counts["failed"] += 1
            except Exception as exc2:  # noqa: BLE001 — row stays sent/in_app
                log.error("notification=%s could not be marked failed: %s",
                          notif_id, exc2)
    return counts


def main() -> int:
    missing = _missing_vars()
    if missing:
        # REQUIRED behaviour while D2 credentials are unavailable:
        # skip quietly, never crash the cron.
        print(f"send_wechat skipped: missing WeChat config:"
              f" {', '.join(missing)}")
        log.info("send_wechat skipped: missing %s", ", ".join(missing))
        return 0
    counts = send_pending()
    print(f"send_wechat done: sent={counts['sent']}"
          f" failed={counts['failed']}"
          f" skipped_no_openid={counts['skipped_no_openid']}")
    log.info("send_wechat done: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
