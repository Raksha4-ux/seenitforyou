"""FastAPI application: health endpoints, manual scan, and background Gmail polling."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.gmail_service import GMAIL_QUERY, GmailService, GmailServiceError
from app.state import ProcessedMessageStore
from app.whatsapp_service import WhatsAppService, WhatsAppServiceError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
store = ProcessedMessageStore(settings.state_file_path)
gmail_service = GmailService(settings)
whatsapp_service = WhatsAppService(settings)

_poll_task: asyncio.Task[None] | None = None
_gmail_ready = False
_last_scan_result: dict[str, Any] = {
    "processed": 0,
    "skipped_duplicates": 0,
    "errors": [],
}


def _ensure_gmail_authenticated() -> None:
    global _gmail_ready
    if not _gmail_ready:
        gmail_service.authenticate()
        _gmail_ready = True


def run_placement_scan() -> dict[str, Any]:
    """Scan Gmail for new unread placement emails and notify via WhatsApp Web."""
    global _last_scan_result

    result: dict[str, Any] = {
        "processed": 0,
        "skipped_duplicates": 0,
        "notified_ids": [],
        "errors": [],
    }

    try:
        _ensure_gmail_authenticated()
        emails = gmail_service.fetch_unread_placement_emails()
    except GmailServiceError as exc:
        logger.error("Gmail scan failed: %s", exc)
        result["errors"].append(str(exc))
        _last_scan_result = result
        return result

    for email in emails:
        message_id = email["id"]

        if store.contains(message_id):
            result["skipped_duplicates"] += 1
            logger.debug("Skipping duplicate message %s", message_id)
            continue

        try:
            parts = whatsapp_service.send_placement_alert(
                sender=email["sender"],
                subject=email["subject"],
                date=email["date"],
                body=email["body"],
            )
            store.add(message_id)
            gmail_service.mark_as_read(message_id)
            result["processed"] += 1
            result["notified_ids"].append(
                {"message_id": message_id, "whatsapp_parts": parts}
            )
            logger.info(
                "Notified placement email %s (%s WhatsApp parts)",
                message_id,
                len(parts),
            )
        except WhatsAppServiceError as exc:
            logger.error("WhatsApp failed for %s: %s", message_id, exc)
            result["errors"].append(f"{message_id}: {exc}")
            break
        except GmailServiceError as exc:
            logger.error("Gmail error after notify for %s: %s", message_id, exc)
            result["errors"].append(f"{message_id}: {exc}")

    _last_scan_result = result
    return result


async def _poll_loop() -> None:
    """Background task: check Gmail every POLL_INTERVAL_SECONDS."""
    interval = settings.poll_interval_seconds
    logger.info("Starting Gmail poll loop (every %s seconds)", interval)

    while True:
        try:
            await asyncio.to_thread(run_placement_scan)
        except Exception as exc:
            logger.exception("Unexpected error in poll loop: %s", exc)

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _poll_task

    try:
        await asyncio.to_thread(_ensure_gmail_authenticated)
    except GmailServiceError as exc:
        logger.warning(
            "Gmail not authenticated at startup (%s). "
            "Complete OAuth when first email is checked or call POST /check.",
            exc,
        )

    try:
        await asyncio.to_thread(whatsapp_service.startup)
    except WhatsAppServiceError as exc:
        logger.warning(
            "WhatsApp Web not ready at startup (%s). "
            "Scan QR in Chrome when prompted, then retry POST /check.",
            exc,
        )

    _poll_task = asyncio.create_task(_poll_loop())
    logger.info("Placement WhatsApp Notifier started")
    yield

    if _poll_task:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass

    await asyncio.to_thread(whatsapp_service.shutdown)
    logger.info("Placement WhatsApp Notifier stopped")


app = FastAPI(
    title="Placement WhatsApp Notifier",
    description="Monitors placement Gmail senders and forwards alerts via WhatsApp Web.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, Any]:
    """Health check and service status."""
    return {
        "status": "ok",
        "service": "Placement WhatsApp Notifier",
        "gmail_authenticated": _gmail_ready,
        "whatsapp_session_ready": whatsapp_service.is_ready,
        "whatsapp_in_cooldown": whatsapp_service.in_cooldown,
        "whatsapp_chat_name": settings.whatsapp_chat_name,
        "poll_interval_seconds": settings.poll_interval_seconds,
        "processed_message_count": store.count(),
        "last_scan": _last_scan_result,
        "gmail_query": GMAIL_QUERY,
    }


@app.post("/check")
def manual_check() -> dict[str, Any]:
    """Manually trigger a Gmail scan and WhatsApp notification pass."""
    try:
        result = run_placement_scan()
    except Exception as exc:
        logger.exception("Manual check failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result["errors"] and result["processed"] == 0:
        raise HTTPException(
            status_code=502,
            detail={"message": "Scan completed with errors", "result": result},
        )

    return {"message": "Scan completed", "result": result}
