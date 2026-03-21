"""
Craigslist RSS scraper.

Polls one or more RSS feed URLs, parses each <item>, stores raw XML
in raw_listings, then upserts structured Apartment rows.

How Craigslist RSS works
────────────────────────
• Append  ?format=rss  to any /search/… URL to get an Atom/RSS feed.
• Each <item> contains: title, link, description (HTML snippet), pubDate,
  dc:date, and encoded:imgTag.
• Useful query params you can bake into the URL:
    max_price, min_price, min_bedrooms, max_bedrooms,
    no_fee=1, availabilityMode=0 (include all), hasPic=1
• The feed returns the 25 newest results; run frequently to avoid gaps.
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import feedparser          # pip install feedparser
import requests

from ..config.settings import settings
from ..db.database import get_db
from ..db.models import Apartment, Host, RawListing, ScrapeRun, SourceEnum, StatusEnum
from ..utils.helpers import (
    clean_text, extract_price, extract_beds_baths,
    extract_sqft, extract_floor, extract_subway_lines,
    url_to_listing_id, detect_borough, geocode_address,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_craigslist_scraper() -> dict:
    """
    Polls all configured RSS URLs, parses entries, and persists results.
    Returns a summary dict for logging / monitoring.
    """
    totals = {"found": 0, "new": 0, "updated": 0, "errors": 0}

    with get_db() as db:
        run = ScrapeRun(source=SourceEnum.craigslist, status="running")
        db.add(run)
        db.flush()

        for feed_url in settings.CRAIGSLIST_RSS_URLS:
            logger.info("Fetching Craigslist RSS: %s", feed_url)
            try:
                stats = _process_feed(feed_url, run.id, db)
                for k in totals:
                    totals[k] += stats.get(k, 0)
            except Exception as exc:
                logger.error("Feed error (%s): %s", feed_url, exc, exc_info=True)
                totals["errors"] += 1

        run.finished_at      = datetime.utcnow()
        run.status           = "success" if totals["errors"] == 0 else "partial"
        run.listings_found   = totals["found"]
        run.listings_new     = totals["new"]
        run.listings_updated = totals["updated"]

    logger.info("Craigslist run done — %s", totals)
    return totals


# ---------------------------------------------------------------------------
# Feed processing
# ---------------------------------------------------------------------------

def _process_feed(feed_url: str, run_id: int, db) -> dict:
    parsed = feedparser.parse(feed_url)
    stats  = {"found": 0, "new": 0, "updated": 0}

    entries = parsed.entries[: settings.CRAIGSLIST_MAX_ITEMS]
    stats["found"] = len(entries)

    for entry in entries:
        try:
            _upsert_entry(entry, feed_url, run_id, db)
            stats["new"] += 1          # simplified; see _upsert_entry return
        except Exception as exc:
            logger.warning("Entry error: %s — %s", entry.get("link"), exc)

    return stats


# ---------------------------------------------------------------------------
# Single entry → Apartment upsert
# ---------------------------------------------------------------------------

def _upsert_entry(entry, feed_url: str, run_id: int, db) -> None:
    link       = entry.get("link", "")
    listing_id = url_to_listing_id(link)

    # ── Raw archive ────────────────────────────────────────────────────────
    raw = RawListing(
        source        = SourceEnum.craigslist,
        scrape_run_id = run_id,
        raw_content   = str(entry),
        content_type  = "rss_entry",
        url           = link,
    )
    db.add(raw)
    db.flush()

    # ── Existing record? ───────────────────────────────────────────────────
    apt = (
        db.query(Apartment)
        .filter_by(source=SourceEnum.craigslist, listing_id=listing_id)
        .first()
    )
    is_new = apt is None
    if is_new:
        apt = Apartment(
            source     = SourceEnum.craigslist,
            listing_id = listing_id,
        )

    # ── Parse fields ────────────────────────────────────────────────────────
    title       = clean_text(entry.get("title", ""))
    description = clean_text(entry.get("summary", ""))
    combined    = f"{title} {description}"

    apt.title            = title
    apt.source_url       = link
    apt.raw_description  = description
    apt.scrape_run_id    = run_id
    apt.status           = StatusEnum.active

    # Price
    apt.price = extract_price(title) or extract_price(description)

    # Beds / baths
    beds, baths = extract_beds_baths(combined)
    apt.bedrooms  = beds
    apt.bathrooms = baths

    # Size
    apt.size_sqft = extract_sqft(combined)

    # Floor
    apt.floor = extract_floor(combined)

    # Borough  (from the feed URL path, e.g. /mnh/ or /brk/)
    path_borough = _borough_from_url(feed_url)
    apt.borough  = path_borough or detect_borough(combined)

    # Subway lines
    lines = extract_subway_lines(combined)
    if lines:
        apt.subway_lines = lines

    # Date listed
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        apt.date_listed = datetime(*published[:6])

    # Images
    imgs = _extract_images(entry)
    if imgs:
        apt.image_urls = imgs

    # Pets
    apt.pets_allowed = _has_keyword(combined, ["pets ok", "pet friendly", "cats ok", "dogs ok"])

    # No-fee
    apt.no_fee = _has_keyword(combined, ["no fee", "no broker fee", "no realtor fee"])

    # Amenities raw list
    apt.amenities_raw = _extract_cl_attributes(entry)

    # Host  (Craigslist hides contact info — we store what we can)
    host = _get_or_create_host(entry, db)
    if host:
        apt.host_id = host.id

    raw.parsed      = True
    raw.apartment_id = apt.id if not is_new else None

    db.add(apt)
    db.flush()

    if is_new:
        raw.apartment_id = apt.id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _borough_from_url(url: str) -> Optional[str]:
    from ..utils.helpers import _BOROUGH_MAP
    path = urlparse(url).path.lower()
    for segment in path.split("/"):
        if segment in _BOROUGH_MAP:
            return _BOROUGH_MAP[segment]
    return None


def _has_keyword(text: str, keywords: list) -> bool:
    low = text.lower()
    return any(k in low for k in keywords)


def _extract_images(entry) -> list:
    """Pull image URLs from <enc:enclosure> or inline <img> tags."""
    imgs = []
    # feedparser sometimes puts images in enclosures
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image"):
            imgs.append(enc["href"])
    # Also scrape from summary HTML
    summary = entry.get("summary", "")
    imgs += re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    return list(dict.fromkeys(imgs))   # deduplicate, preserve order


def _extract_cl_attributes(entry) -> list:
    """
    Craigslist sometimes includes structured attributes in tags
    like <cl:attrs> or as plain text bullets.
    """
    attrs = []
    raw = entry.get("summary", "")
    # Bullet-like patterns: "- laundry in bldg", "/ cats are OK"
    for m in re.finditer(r"[-•/]\s*([^<\n\r]{3,60})", raw):
        attrs.append(m.group(1).strip())
    return attrs[:20]   # cap at 20


def _get_or_create_host(entry, db) -> Optional[Host]:
    """
    Craigslist anonymises emails; we store the author name if available.
    """
    author = entry.get("author", "").strip()
    if not author:
        return None
    host = db.query(Host).filter_by(name=author).first()
    if not host:
        host = Host(name=author)
        db.add(host)
        db.flush()
    return host