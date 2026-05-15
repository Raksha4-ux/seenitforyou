"""Gmail API integration: OAuth2 auth and unread placement-email fetching."""

import logging
from typing import Any

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings
from app.parser import parse_gmail_message

logger = logging.getLogger(__name__)

# Strict query: only unread from allowed placement senders.
ALLOWED_SENDERS = (
    "cvr.placement@gmail.com",
    "alerts@haveloc.com",
    "vishwanathraksha37@gmail.com",
)

GMAIL_QUERY = " OR ".join(f"(is:unread from:{sender})" for sender in ALLOWED_SENDERS)


class GmailServiceError(Exception):
    """Raised when Gmail authentication or API calls fail."""


class GmailService:
    """Authenticate with Gmail and fetch placement-related unread messages only."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service: Any | None = None

    def authenticate(self) -> None:
        """Build Gmail API client using OAuth2 credentials."""
        creds: Credentials | None = None
        token_path = self._settings.gmail_token_path
        credentials_path = self._settings.gmail_credentials_path
        scopes = self._settings.gmail_scope_list

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), scopes)
            except (ValueError, OSError) as exc:
                logger.warning("Invalid token file, re-auth required: %s", exc)
                creds = None

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except GoogleAuthError as exc:
                raise GmailServiceError(f"Gmail token refresh failed: {exc}") from exc

        if not creds or not creds.valid:
            if not credentials_path.exists():
                raise GmailServiceError(
                    f"Missing {credentials_path}. Download OAuth client JSON from "
                    "Google Cloud Console and save as credentials.json."
                )
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), scopes
                )
                creds = flow.run_local_server(port=0)
            except (GoogleAuthError, OSError, ValueError) as exc:
                raise GmailServiceError(f"Gmail OAuth flow failed: {exc}") from exc

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        try:
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        except Exception as exc:
            raise GmailServiceError(f"Failed to build Gmail client: {exc}") from exc

        logger.info("Gmail API authenticated successfully")

    @property
    def service(self) -> Any:
        if self._service is None:
            raise GmailServiceError("Gmail client not authenticated. Call authenticate() first.")
        return self._service

    def list_unread_placement_message_ids(self) -> list[str]:
        """List IDs of unread emails matching the strict placement sender query."""
        try:
            response = (
                self.service.users()
                .messages()
                .list(userId="me", q=GMAIL_QUERY, maxResults=50)
                .execute()
            )
        except HttpError as exc:
            raise GmailServiceError(f"Gmail list messages failed: {exc}") from exc
        except OSError as exc:
            raise GmailServiceError(f"Network error listing Gmail messages: {exc}") from exc

        messages = response.get("messages", []) or []
        return [m["id"] for m in messages if m.get("id")]

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Fetch full message by ID."""
        try:
            return (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as exc:
            raise GmailServiceError(
                f"Gmail get message {message_id} failed: {exc}"
            ) from exc
        except OSError as exc:
            raise GmailServiceError(
                f"Network error fetching message {message_id}: {exc}"
            ) from exc

    def mark_as_read(self, message_id: str) -> None:
        """Remove UNREAD label so the same email is not picked up again."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        except HttpError as exc:
            logger.warning("Could not mark message %s as read: %s", message_id, exc)

    def fetch_unread_placement_emails(self) -> list[dict[str, str]]:
        """Return parsed email dicts for all unread placement messages."""
        ids = self.list_unread_placement_message_ids()
        results: list[dict[str, str]] = []

        for message_id in ids:
            raw = self.get_message(message_id)
            parsed = parse_gmail_message(raw)
            results.append(parsed)

        return results
