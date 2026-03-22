"""
StreetEasy Email Parser
=======================
Parses StreetEasy saved-search alert emails fetched via the Gmail API
and converts them into Apartment (+ NeighborInfo) records ready for
upsert into the database.

Usage
-----
    from parser import StreetEasyEmailParser

    parser = StreetEasyEmailParser()

    # From a raw Gmail message dict (as returned by Gmail API)
    listings = parser.parse_gmail_message(gmail_message)

    # From a raw .eml file (for testing / offline use)
    listings = parser.parse_eml_file("path/to/message.eml")

Each call returns a list of ParsedListing dataclass instances.
"""

from __future__ import annotations

import base64
import email
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class ParsedListing:
    """
    Flat representation of one apartment listing extracted from a
    StreetEasy alert email.  Maps directly onto the Apartment model;
    neighborhood_name is used to look-up / create NeighborInfo rows.
    """
    # Core identity
    streeteasy_id: str                   # numeric ID from the listing URL
    streeteasy_url: str

    # Apartment fields
    name: str                            # full address string, e.g. "45-15 43rd Avenue #4A"
    bedroom_type: str                    # "Studio", "1 Bed", "2 Bed", …
    price: int                           # monthly base rent in USD

    # Neighbourhood
    neighborhood_name: str               # plain string; caller resolves/creates NeighborInfo

    # Optional fields (populated when available in the email)
    bathrooms: Optional[int] = None
    host_contact: Optional[str] = None   # brokerage name + address

    # Metadata extracted from the email envelope
    email_subject: str = ""
    email_date: Optional[datetime] = None
    email_message_id: str = ""

    # Fields that are not in the email but required by the schema —
    # the caller / AI agent must fill these in later.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    move_in_date: Optional[str] = None
    lease_length_months: Optional[int] = None
    laundry: list[str] = field(default_factory=list)
    parking: list[str] = field(default_factory=list)
    amenities: list[str] = field(default_factory=list)
    pets: bool = False
    images: list[str] = field(default_factory=list)
    image_labels: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class StreetEasyEmailParser:
    """
    Parses StreetEasy saved-search alert emails.

    StreetEasy wraps all outbound links through their click-tracker
    (links.streeteasy.com), so we extract listing data from the *plain-text*
    part of the email, which preserves the original streeteasy.com/rental/<id>
    URLs.
    """

    # Sender domains used to validate that this is actually a StreetEasy email.
    SENDER_DOMAINS = {"streeteasy.com", "email.streeteasy.com"}

    # Regex: one listing block in the plain-text part.
    # StreetEasy plain-text format (as observed):
    #
    #   Rental Unit in <Neighborhood>
    #   <Address>
    #    $<price> base rent
    #
    #   <beds>
    #    <baths>
    #    <brokerage name + address>
    #   <https://streeteasy.com/rental/<id>>
    _LISTING_BLOCK_RE = re.compile(
        r"Rental Unit in ([^\n]+)\n"        # group 1: neighborhood
        r"([^\n]+)\n"                        # group 2: address
        r"\s*\$([\d,]+)\s+base rent",        # group 3: price (dollars, no cents)
        re.MULTILINE,
    )

    _BEDS_RE = re.compile(r"(\d+)\s*Bed|Studio", re.IGNORECASE)
    _BATHS_RE = re.compile(r"(\d+)\s*Bath", re.IGNORECASE)
    _RENTAL_URL_RE = re.compile(r"https://streeteasy\.com/rental/(\d+)")
    _BROKERAGE_RE = re.compile(r"<https://streeteasy\.com/rental/\d+>")

    # ---------------------------------------------------------------------------

    def parse_gmail_message(self, gmail_message: dict) -> list[ParsedListing]:
        """
        Parse a message dict as returned by the Gmail API
        (users.messages.get with format='raw').

        Parameters
        ----------
        gmail_message:
            Dict with at least a 'raw' key containing the base64url-encoded
            RFC 2822 message, and optionally 'id' and 'internalDate'.

        Returns
        -------
        List of ParsedListing instances (empty list if nothing found or the
        email is not a StreetEasy alert).
        """
        raw_bytes = base64.urlsafe_b64decode(
            gmail_message.get("raw", "") + "=="  # padding is idempotent
        )
        gmail_id = gmail_message.get("id", "")
        return self._parse_bytes(raw_bytes, gmail_id=gmail_id)

    def parse_eml_file(self, path: str) -> list[ParsedListing]:
        """
        Parse a .eml file from disk (useful for local testing).
        """
        with open(path, "rb") as fh:
            raw_bytes = fh.read()
        return self._parse_bytes(raw_bytes)

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    def _parse_bytes(
        self, raw_bytes: bytes, gmail_id: str = ""
    ) -> list[ParsedListing]:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)

        if not self._is_streeteasy_alert(msg):
            logger.debug("Skipping non-StreetEasy email (id=%s)", gmail_id)
            return []

        subject = str(msg.get("subject", ""))
        date = self._parse_date(msg.get("date"))
        message_id = str(msg.get("message-id", gmail_id))

        plain_text = self._get_plain_text(msg)
        if not plain_text:
            logger.warning("No plain-text part found in message id=%s", message_id)
            return []

        listings = self._extract_listings(plain_text)

        # Attach email metadata to every listing.
        for listing in listings:
            listing.email_subject = subject
            listing.email_date = date
            listing.email_message_id = message_id

        logger.info(
            "Parsed %d listing(s) from email '%s'", len(listings), subject
        )
        return listings

    # ---- Validation ----

    def _is_streeteasy_alert(self, msg: email.message.Message) -> bool:
        """Return True only for genuine StreetEasy saved-search alert emails."""
        sender = str(msg.get("from", ""))
        reply_to = str(msg.get("reply-to", ""))
        subject = str(msg.get("subject", ""))

        domain_ok = any(
            domain in sender or domain in reply_to
            for domain in self.SENDER_DOMAINS
        )
        # StreetEasy alert subjects always contain "Results for" or "new to market"
        subject_ok = bool(
            re.search(r"results for|saved search|new to market", subject, re.IGNORECASE)
        )
        return domain_ok or subject_ok

    # ---- Email body extraction ----

    def _get_plain_text(self, msg: email.message.Message) -> str:
        """Return the decoded plain-text body, preferring text/plain."""
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_content()
        # Fallback: strip HTML tags if no plain-text part exists.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                soup = BeautifulSoup(part.get_content(), "html.parser")
                return soup.get_text(separator="\n")
        return ""

    # ---- Listing extraction ----

    def _extract_listings(self, plain_text: str) -> list[ParsedListing]:
        """
        Split the plain-text body into per-listing blocks and parse each one.

        Strategy: split on "Rental Unit in " — each segment that follows is
        one listing card ending at (or before) the next "Rental Unit in ".
        The first segment (before the first match) is the email header and
        is discarded.
        """
        # Split into blocks
        blocks = re.split(r"Rental Unit in ", plain_text)
        if len(blocks) < 2:
            logger.debug("No 'Rental Unit in' markers found in plain text.")
            return []

        listings: list[ParsedListing] = []
        for raw_block in blocks[1:]:
            try:
                listing = self._parse_listing_block(raw_block)
                if listing:
                    listings.append(listing)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse listing block: %s", exc, exc_info=True)

        return listings

    def _parse_listing_block(self, block: str) -> Optional[ParsedListing]:
        """
        Parse a single listing block.

        Expected block structure (after "Rental Unit in " has been stripped):

            Sunnyside
            45-15 43rd Avenue #4A
             $2,300 base rent


             1 Bed
             1 Bath
             Voro New York (1129 Northern Boulevard, Manhasset, NY 11030)
            <https://streeteasy.com/rental/4995742>
        """
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 4:
            return None

        # Line 0: neighborhood
        neighborhood = lines[0]

        # Line 1: address
        address = lines[1]

        # Line 2: price  — "$2,300 base rent"
        price_match = re.search(r"\$([\d,]+)\s+base rent", lines[2], re.IGNORECASE)
        if not price_match:
            logger.debug("No price found in block starting with: %s", lines[:3])
            return None
        price = int(price_match.group(1).replace(",", ""))

        # Lines 3+: beds, baths, brokerage, URL (order is consistent but
        # we scan rather than assume exact positions).
        bedroom_type = "Unknown"
        bathrooms: Optional[int] = None
        host_contact: Optional[str] = None
        streeteasy_url: Optional[str] = None
        streeteasy_id: Optional[str] = None

        for line in lines[3:]:
            # Beds
            bed_match = self._BEDS_RE.search(line)
            if bed_match and bedroom_type == "Unknown":
                if "studio" in line.lower():
                    bedroom_type = "Studio"
                else:
                    bedroom_type = f"{bed_match.group(1)} Bed"
                continue

            # Baths
            bath_match = self._BATHS_RE.search(line)
            if bath_match and bathrooms is None:
                bathrooms = int(bath_match.group(1))
                continue

            # Listing URL  — <https://streeteasy.com/rental/4995742>
            url_match = self._RENTAL_URL_RE.search(line)
            if url_match and streeteasy_id is None:
                streeteasy_url = url_match.group(0)
                streeteasy_id = url_match.group(1)
                continue

            # Brokerage / agent contact — everything that isn't beds/baths/URL
            # and looks like "Agency Name (address)"
            if re.search(r"\(.*\)", line) and host_contact is None:
                host_contact = line

        if not streeteasy_id:
            logger.debug("No StreetEasy listing URL found in block: %s", lines)
            return None

        return ParsedListing(
            streeteasy_id=streeteasy_id,
            streeteasy_url=streeteasy_url,
            name=address,
            bedroom_type=bedroom_type,
            price=price,
            neighborhood_name=neighborhood,
            bathrooms=bathrooms,
            host_contact=host_contact,
        )

    # ---- Date parsing ----

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return None