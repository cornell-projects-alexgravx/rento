"""Poll Gmail for host replies to agent3 outbound inquiry emails.

How it works
------------
When agent3 sends an inquiry it sets:
    Reply-To: <smtp_local>+<match_id>@<smtp_domain>

When the host hits "reply", their client addresses the email to that
subaddress. Gmail delivers it to the base inbox and preserves the
subaddress in the Delivered-To / To header.

This module runs as an APScheduler job every GMAIL_REPLY_POLL_INTERVAL_S
seconds. It queries Gmail for unread messages whose subject starts with
"Re: Apartment Inquiry:", extracts the match_id from the subaddress in
the Delivered-To header, and inserts a Message(type="host") row so that
agent3's poll_for_reply node picks it up from the DB.

Gmail credentials
-----------------
Set GMAIL_CREDENTIALS_PATH and GMAIL_TOKEN_PATH in the environment.
On first run the OAuth flow opens a browser; subsequent runs reuse the
stored token. If either path is missing the poller silently skips.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Matches the UUID embedded in a Gmail subaddress: local+<uuid>@domain
_MATCH_ID_RE = re.compile(r"\+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})@", re.IGNORECASE)

# Gmail search query: unread replies to our outbound inquiries, not sent by us.
_GMAIL_QUERY = 'subject:"Re: Apartment Inquiry:" is:unread -from:me'


def _get_gmail_service(credentials_path: str, token_path: str):
    """Build and return an authenticated Gmail API service (sync)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/gmail.modify"]
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Gmail credentials not found at {credentials_path}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _extract_match_id(header_value: str) -> str | None:
    m = _MATCH_ID_RE.search(header_value)
    return m.group(1) if m else None


def _decode_plain_text(payload: dict) -> str:
    """Recursively extract the first text/plain body from a Gmail payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _decode_plain_text(part)
        if result:
            return result
    return ""


def _fetch_replies_sync(credentials_path: str, token_path: str) -> list[dict]:
    """Fetch unread host-reply emails from Gmail and mark them read (sync).

    Returns a list of dicts with keys: match_id, body, external_id, gmail_id.
    """
    try:
        service = _get_gmail_service(credentials_path, token_path)
    except FileNotFoundError as exc:
        logger.warning("Gmail credentials missing — skipping reply poll: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Gmail auth failed: %s", exc)
        return []

    response = service.users().messages().list(userId="me", q=_GMAIL_QUERY, maxResults=50).execute()
    stubs = response.get("messages", [])
    if not stubs:
        return []

    logger.info("Gmail poller: found %d unread reply email(s)", len(stubs))
    results: list[dict] = []

    for stub in stubs:
        gmail_id = stub["id"]
        try:
            msg = service.users().messages().get(
                userId="me", id=gmail_id, format="full"
            ).execute()

            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }

            # Try Delivered-To first (most reliable for subaddress routing),
            # then fall back to To and X-Original-To.
            match_id = (
                _extract_match_id(headers.get("delivered-to", ""))
                or _extract_match_id(headers.get("to", ""))
                or _extract_match_id(headers.get("x-original-to", ""))
            )

            if not match_id:
                logger.debug(
                    "Gmail poller: no match_id in headers of message %s "
                    "(delivered-to=%r, to=%r) — skipping",
                    gmail_id,
                    headers.get("delivered-to"),
                    headers.get("to"),
                )
                # Mark read so it doesn't clog the queue.
                _mark_read(service, gmail_id)
                continue

            body = _decode_plain_text(msg.get("payload", {})).strip()
            if not body:
                body = msg.get("snippet", "").strip()

            external_id = headers.get("message-id", gmail_id)

            results.append({
                "match_id": match_id,
                "body": body,
                "external_id": external_id,
                "gmail_id": gmail_id,
                "service": service,
            })
        except Exception as exc:
            logger.warning("Gmail poller: error processing message %s: %s", gmail_id, exc)

    return results


def _mark_read(service, gmail_id: str) -> None:
    try:
        service.users().messages().modify(
            userId="me", id=gmail_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    except Exception as exc:
        logger.warning("Gmail poller: failed to mark %s as read: %s", gmail_id, exc)


async def poll_host_replies() -> None:
    """Entry point called by the APScheduler job.

    Fetches Gmail replies in a thread (sync API), then writes new
    Message(type="host") rows to the DB asynchronously.
    """
    from app.constants import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH
    from app.database import async_session_factory
    from app.models.match import Match
    from app.models.message import Message
    from sqlalchemy import select

    if not os.path.exists(GMAIL_CREDENTIALS_PATH) and not os.path.exists(GMAIL_TOKEN_PATH):
        logger.debug("Gmail credentials not configured — skipping host reply poll")
        return

    # Run synchronous Gmail API calls in a thread pool to avoid blocking the
    # asyncio event loop.
    raw_replies = await asyncio.to_thread(
        _fetch_replies_sync, GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH
    )

    if not raw_replies:
        return

    async with async_session_factory() as session:
        for reply in raw_replies:
            match_id: str = reply["match_id"]
            external_id: str = reply["external_id"]
            service = reply["service"]
            gmail_id: str = reply["gmail_id"]

            try:
                # Verify the match exists.
                match = await session.get(Match, match_id)
                if not match:
                    logger.warning("Gmail poller: match_id %s not found in DB", match_id)
                    _mark_read(service, gmail_id)
                    continue

                # Idempotency: skip if we already inserted this email.
                existing = (
                    await session.execute(
                        select(Message).where(
                            Message.match_id == match_id,
                            Message.type == "host",
                            Message.external_id == external_id,
                        ).limit(1)
                    )
                ).scalar_one_or_none()

                if existing:
                    _mark_read(service, gmail_id)
                    continue

                msg = Message(
                    id=str(uuid.uuid4()),
                    match_id=match_id,
                    type="host",
                    timestamp=datetime.now(tz=timezone.utc),
                    text=reply["body"],
                    external_id=external_id,
                )
                session.add(msg)
                await session.commit()

                _mark_read(service, gmail_id)
                logger.info("Gmail poller: inserted host reply for match %s", match_id)

            except Exception as exc:
                logger.warning(
                    "Gmail poller: DB error for match %s: %s", match_id, exc
                )
                await session.rollback()
