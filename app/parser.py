"""Email body extraction from Gmail API payloads (plain text and HTML)."""

import base64
import logging
import re
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

WHITESPACE_RE = re.compile(r"\n{3,}")
SPACE_RE = re.compile(r"[ \t]+\n")


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
    return raw.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = SPACE_RE.sub("\n", text)
    text = WHITESPACE_RE.sub("\n\n", text)
    return text.strip()


def _collect_parts(
    payload: dict[str, Any],
    plain_parts: list[str],
    html_parts: list[str],
) -> None:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")

    if data:
        decoded = _decode_base64url(data)
        if mime_type == "text/plain":
            plain_parts.append(decoded)
        elif mime_type == "text/html":
            html_parts.append(decoded)

    for part in payload.get("parts", []) or []:
        _collect_parts(part, plain_parts, html_parts)


def extract_body_from_payload(payload: dict[str, Any]) -> str:
    """Prefer text/plain; fall back to HTML converted to readable plain text."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_parts(payload, plain_parts, html_parts)

    if plain_parts:
        return _clean_text("\n\n".join(plain_parts))

    if html_parts:
        converted = [_html_to_text(part) for part in html_parts]
        return _clean_text("\n\n".join(converted))

    snippet = payload.get("body", {}).get("data")
    if snippet:
        return _clean_text(_decode_base64url(snippet))

    return ""


def extract_header(headers: list[dict[str, str]], name: str) -> str:
    name_lower = name.lower()
    for header in headers:
        if header.get("name", "").lower() == name_lower:
            return header.get("value", "").strip()
    return ""


def format_date(internal_date_ms: str | None, date_header: str) -> str:
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
            return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except (TypeError, ValueError, OverflowError):
            pass

    if internal_date_ms:
        try:
            from datetime import datetime, timezone

            ms = int(internal_date_ms)
            dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (TypeError, ValueError, OSError):
            pass

    return "Unknown"


def parse_gmail_message(message: dict[str, Any]) -> dict[str, str]:
    """Parse a Gmail API message resource into notification fields."""
    message_id = message.get("id", "")
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    sender = extract_header(headers, "From")
    subject = extract_header(headers, "Subject") or "(No subject)"
    date_header = extract_header(headers, "Date")
    internal_date = message.get("internalDate")
    date_str = format_date(internal_date, date_header)

    body = extract_body_from_payload(payload)
    if not body:
        body = "(Email had no readable body content)"
        logger.warning("Empty body for message %s", message_id)

    return {
        "id": message_id,
        "sender": sender,
        "subject": subject,
        "date": date_str,
        "body": body,
    }
