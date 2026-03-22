"""
Gmail API parser for StreetEasy listing-alert emails.

How StreetEasy email alerts work
─────────────────────────────────
• Go to StreetEasy → set your filters → click "Save Search" → enable email alerts.
• You'll receive emails from alerts@streeteasy.com with subject like:
  "5 new listings match your search in Manhattan"
• Each email contains HTML cards with: photo, address, price, beds/baths,
  link to the listing, and brief details.

Gmail OAuth2 Setup (one-time — 5 minutes)
──────────────────────────────────────────
1. Go to https://console.cloud.google.com
2. Create a new project (or pick an existing one).
3. Enable the Gmail API:
   APIs & Services → Library → search "Gmail API" → Enable
4. Create OAuth2 credentials:
   APIs & Services → Credentials → Create Credentials → OAuth client ID
   Application type: Desktop app → Download JSON → save as  credentials.json
5. Add  GMAIL_CREDENTIALS_FILE=credentials.json  to your .env
6. First run will open a browser for Google login — token saved to token.json
   (subsequent runs are fully automatic).

Required scopes:  gmail.readonly  (read-only — we never modify your mailbox)

pip install  google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import base64
import logging
import re
from datetime import datetime, UTC
from email import message_from_bytes
from typing import Optional, List

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..config.settings import settings
from ..db.database import get_db
from ..db.models import (
    Apartment, Host, RawListing, ScrapeRun,
    SourceEnum, StatusEnum,
)
from ..utils.helpers import (
    clean_text, extract_price, extract_beds_baths,
    extract_sqft, url_to_listing_id, detect_borough,
    geocode_address,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_gmail_parser() -> dict:
    totals = {"found": 0, "new": 0, "updated": 0, "errors": 0}

    service = _get_gmail_service()
    if not service:
        logger.error("Could not authenticate with Gmail — skipping email parse.")
        return totals

    with get_db() as db:
        run = ScrapeRun(source=SourceEnum.streeteasy_email, status="running")
        db.add(run)
        db.flush()

        try:
            message_ids = _fetch_unread_alert_ids(service)
            totals["found"] = len(message_ids)
            logger.info("Gmail: found %d StreetEasy alert emails", len(message_ids))

            for msg_id in message_ids:
                try:
                    stats = _process_message(service, msg_id, run.id, db)
                    for k in ("new", "updated"):
                        totals[k] += stats.get(k, 0)
                    # Mark email as read so we don't re-process it
                    service.users().messages().modify(
                        userId="me", id=msg_id,
                        body={"removeLabelIds": ["UNREAD"]}
                    ).execute()
                except Exception as exc:
                    logger.warning("Email %s error: %s", msg_id, exc, exc_info=True)
                    totals["errors"] += 1

        except Exception as exc:
            logger.error("Gmail parse failed: %s", exc, exc_info=True)
            run.error_message = str(exc)
            totals["errors"] += 1

        run.finished_at      = datetime.now(UTC)
        run.status           = "success" if totals["errors"] == 0 else "partial"
        run.listings_found   = totals["found"]
        run.listings_new     = totals["new"]
        run.listings_updated = totals["updated"]

    logger.info("Gmail run done — %s", totals)
    return totals


# ---------------------------------------------------------------------------
# Gmail API authentication
# ---------------------------------------------------------------------------

def _get_gmail_service():
    """Return an authenticated Gmail API service object."""
    import os
    creds = None
    token_file = settings.GMAIL_TOKEN_FILE
    creds_file = settings.GMAIL_CREDENTIALS_FILE

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_file):
                logger.error(
                    "Gmail credentials file not found: %s\n"
                    "See docstring for setup instructions.", creds_file
                )
                return None
            flow  = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Fetch unread alert message IDs
# ---------------------------------------------------------------------------

def _fetch_unread_alert_ids(service) -> List[str]:
    query   = settings.GMAIL_SEARCH_QUERY + " is:unread"
    result  = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
    msgs    = result.get("messages", [])
    return [m["id"] for m in msgs]


# ---------------------------------------------------------------------------
# Process one email → N listings
# ---------------------------------------------------------------------------

def _process_message(service, msg_id: str, run_id: int, db) -> dict:
    raw_msg  = service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
    raw_data = base64.urlsafe_b64decode(raw_msg["raw"])
    email    = message_from_bytes(raw_data)

    html_body = _get_html_body(email)
    if not html_body:
        logger.debug("Email %s has no HTML body — skipping.", msg_id)
        return {}

    # Archive raw email
    raw_rec = RawListing(
        source        = SourceEnum.streeteasy_email,
        scrape_run_id = run_id,
        raw_content   = html_body,
        content_type  = "email",
        url           = f"gmail:message:{msg_id}",
    )
    db.add(raw_rec)
    db.flush()

    # Parse listing cards from HTML
    soup    = BeautifulSoup(html_body, "html.parser")
    cards   = _find_listing_cards(soup)
    stats   = {"new": 0, "updated": 0}

    for card in cards:
        try:
            is_new = _upsert_card(card, run_id, db)
            if is_new:
                stats["new"] += 1
            else:
                stats["updated"] += 1
        except Exception as exc:
            logger.warning("Card parse error: %s", exc)

    raw_rec.parsed = True
    return stats


# ---------------------------------------------------------------------------
# Email body helpers
# ---------------------------------------------------------------------------

def _get_html_body(email) -> Optional[str]:
    """Walk MIME parts and return the first HTML body."""
    if email.is_multipart():
        for part in email.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = email.get_payload(decode=True)
        if payload:
            return payload.decode(email.get_content_charset() or "utf-8", errors="replace")
    return None


# ---------------------------------------------------------------------------
# Listing card detection
# ---------------------------------------------------------------------------

def _find_listing_cards(soup: BeautifulSoup) -> list:
    """
    StreetEasy alert emails use table-based HTML.
    Each listing is usually a <td> or <div> block that contains a price,
    an address, and a link to streeteasy.com.
    """
    cards = []
    # Heuristic: any block that contains a StreetEasy listing link
    for el in soup.find_all(href=re.compile(r"streeteasy\.com/(for-rent|rental)/\d")):
        # Walk up to a container with enough context
        container = el
        for _ in range(4):
            p = container.parent
            if p and len(p.get_text()) > len(container.get_text()):
                container = p
            else:
                break
        cards.append(container)
    return cards


# ---------------------------------------------------------------------------
# Card → Apartment upsert
# ---------------------------------------------------------------------------

def _upsert_card(card, run_id: int, db) -> bool:
    """Parse one listing card and upsert into Apartment. Returns True if new."""
    text = card.get_text(" ")

    # URL & listing ID
    link_el    = card.find(href=re.compile(r"streeteasy\.com"))
    url        = link_el["href"] if link_el else ""
    listing_id = url_to_listing_id(url) if url else None
    if not listing_id:
        return False

    apt    = db.query(Apartment).filter_by(
        source=SourceEnum.streeteasy_email, listing_id=listing_id
    ).first()
    # Also check if already scraped via web scraper to avoid duplicates
    if not apt:
        apt = db.query(Apartment).filter_by(
            source=SourceEnum.streeteasy, listing_id=listing_id
        ).first()
        if apt:
            # Update existing web-scraped record instead of creating duplicate
            apt.date_updated = datetime.utcnow()
            return False

    is_new = apt is None
    if is_new:
        apt = Apartment(source=SourceEnum.streeteasy_email, listing_id=listing_id)

    apt.source_url    = url
    apt.scrape_run_id = run_id
    apt.status        = StatusEnum.active

    # Price
    apt.price = extract_price(text)

    # Address (first line-ish before the price)
    addr_m = re.search(r"\d+\s+[\w\s]+(?:St|Ave|Blvd|Rd|Dr|Pl|Ln|Way|Ct|Ter)[^\n,]*", text, re.I)
    if addr_m:
        apt.full_address = addr_m.group(0).strip()

    # Beds / baths
    beds, baths = extract_beds_baths(text)
    apt.bedrooms  = beds
    apt.bathrooms = baths

    # Sqft
    apt.size_sqft = extract_sqft(text)

    # Borough
    apt.borough = detect_borough(text)

    # Neighborhood
    nbhd_m = re.search(r"in\s+([A-Z][a-zA-Z\s]{3,25}),?\s+(?:Manhattan|Brooklyn|Queens|Bronx)", text)
    if nbhd_m:
        apt.neighborhood = nbhd_m.group(1).strip()

    # Raw description (full card text)
    apt.raw_description = clean_text(text)

    # Image
    img_el = card.find("img")
    if img_el and img_el.get("src"):
        apt.image_urls = [img_el["src"]]

    # No-fee
    apt.no_fee = bool(re.search(r"no\s+fee", text, re.I))

    # Geocode
    if apt.full_address and not apt.lat and settings.GEOCODE_ENABLED:
        apt.lat, apt.lng = geocode_address(apt.full_address)

    db.add(apt)
    db.flush()
    return is_new