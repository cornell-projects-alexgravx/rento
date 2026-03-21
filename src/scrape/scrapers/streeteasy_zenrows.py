"""
StreetEasy scraper — powered by ZenRows.

ZenRows handles headless rendering, CAPTCHA solving, and rotating proxies
so StreetEasy's bot-detection doesn't block us.

Setup (one-time)
────────────────
1. Sign up at https://www.zenrows.com  (free tier: 1 000 credits/month)
2. Copy your API key from the dashboard → Settings → API Key
3. Add  ZENROWS_API_KEY=<key>  to your .env file

ZenRows pricing (as of 2025)
─────────────────────────────
• Free:    1 000 API credits / month
• Starter: 250 000 credits  — ~$49/mo
• Each JS-rendered request costs 5 credits; plain HTML costs 1.
• StreetEasy requires JS rendering, so budget ~5 credits/page.
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional, List
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

from ..config.settings import settings
from ..db.database import get_db
from ..db.models import (
    Apartment, Host, RawListing, ScrapeRun,
    SourceEnum, StatusEnum, BuildingTypeEnum,
)
from ..utils.helpers import (
    clean_text, extract_price, extract_beds_baths,
    extract_sqft, extract_floor, extract_subway_lines,
    url_to_listing_id, detect_borough, geocode_address,
)

logger = logging.getLogger(__name__)

ZENROWS_API  = "https://api.zenrows.com/v1/"
SE_BASE      = "https://streeteasy.com"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_streeteasy_scraper() -> dict:
    totals = {"found": 0, "new": 0, "updated": 0, "errors": 0}

    if not settings.ZENROWS_API_KEY:
        logger.error("ZENROWS_API_KEY is not set — skipping StreetEasy scrape.")
        return totals

    with get_db() as db:
        run = ScrapeRun(source=SourceEnum.streeteasy, status="running")
        db.add(run)
        db.flush()

        try:
            urls = _collect_listing_urls(settings.STREETEASY_SEARCH_URL)
            totals["found"] = len(urls)
            logger.info("StreetEasy: found %d listing URLs", len(urls))

            for url in urls:
                try:
                    stats = _scrape_listing(url, run.id, db)
                    for k in ("new", "updated"):
                        totals[k] += stats.get(k, 0)
                    time.sleep(1.5)   # be polite (ZenRows handles rotating, but still)
                except Exception as exc:
                    logger.warning("Listing error (%s): %s", url, exc)
                    totals["errors"] += 1

        except Exception as exc:
            logger.error("StreetEasy scrape failed: %s", exc, exc_info=True)
            run.error_message = str(exc)
            totals["errors"] += 1

        run.finished_at      = datetime.utcnow()
        run.status           = "success" if totals["errors"] == 0 else "partial"
        run.listings_found   = totals["found"]
        run.listings_new     = totals["new"]
        run.listings_updated = totals["updated"]

    logger.info("StreetEasy run done — %s", totals)
    return totals


# ---------------------------------------------------------------------------
# Step 1: Collect listing URLs from search results pages
# ---------------------------------------------------------------------------

def _collect_listing_urls(search_url: str) -> List[str]:
    """
    Paginate through StreetEasy search results and return individual
    listing URLs.  StreetEasy uses  ?page=N  for pagination.
    """
    urls = []
    for page in range(1, settings.STREETEASY_MAX_PAGES + 1):
        page_url = f"{search_url}&page={page}" if "?" in search_url else f"{search_url}?page={page}"
        html     = _zenrows_fetch(page_url, js_render=True)
        if not html:
            break

        soup  = BeautifulSoup(html, "html.parser")
        links = _extract_listing_links(soup)
        if not links:
            logger.info("No more listings on page %d — stopping pagination.", page)
            break

        urls.extend(links)
        logger.debug("Page %d: found %d links", page, len(links))
        time.sleep(2)

    return list(dict.fromkeys(urls))   # dedup, preserve order


def _extract_listing_links(soup: BeautifulSoup) -> List[str]:
    """Pull listing URLs from a search-results page."""
    links = []
    # StreetEasy listing cards use  <a class="...listing-title...">
    for a in soup.select("a[href*='/for-rent/'], a[href*='/rental/']"):
        href = a.get("href", "")
        if href and re.search(r"/\d{5,}", href):   # must contain a listing ID
            full = urljoin(SE_BASE, href)
            links.append(full)
    return links


# ---------------------------------------------------------------------------
# Step 2: Scrape a single listing page
# ---------------------------------------------------------------------------

def _scrape_listing(url: str, run_id: int, db) -> dict:
    html       = _zenrows_fetch(url, js_render=True)
    if not html:
        return {}

    listing_id = url_to_listing_id(url)

    # Archive raw HTML
    raw = RawListing(
        source        = SourceEnum.streeteasy,
        scrape_run_id = run_id,
        raw_content   = html,
        content_type  = "html",
        url           = url,
    )
    db.add(raw)
    db.flush()

    # Existing record?
    apt    = db.query(Apartment).filter_by(source=SourceEnum.streeteasy, listing_id=listing_id).first()
    is_new = apt is None
    if is_new:
        apt = Apartment(source=SourceEnum.streeteasy, listing_id=listing_id)

    soup = BeautifulSoup(html, "html.parser")
    _parse_listing_page(soup, apt, url)
    apt.scrape_run_id = run_id
    apt.status        = StatusEnum.active
    apt.date_scraped  = datetime.utcnow()

    # Host
    host = _parse_host(soup, db)
    if host:
        apt.host_id = host.id

    # Geocode if no coords yet
    if apt.full_address and not apt.lat and settings.GEOCODE_ENABLED:
        apt.lat, apt.lng = geocode_address(apt.full_address)

    raw.parsed      = True
    db.add(apt)
    db.flush()
    raw.apartment_id = apt.id

    return {"new": 1 if is_new else 0, "updated": 0 if is_new else 1}


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _parse_listing_page(soup: BeautifulSoup, apt: Apartment, url: str) -> None:
    """Extract all structured fields from a StreetEasy listing page."""

    apt.source_url = url

    # Title
    h1 = soup.find("h1")
    apt.title = clean_text(h1.get_text()) if h1 else None

    # Price
    price_el = (
        soup.select_one("[data-testid='price']")
        or soup.select_one(".price")
        or soup.find(class_=re.compile(r"price", re.I))
    )
    if price_el:
        apt.price = extract_price(price_el.get_text())

    # Details summary line: "2 beds · 1 bath · 850 ft²"
    details = soup.select_one("[data-testid='listing-detail-summary']") or \
              soup.find(class_=re.compile(r"detail.summary|unit.detail", re.I))
    if details:
        detail_text = details.get_text(" ")
        beds, baths = extract_beds_baths(detail_text)
        apt.bedrooms  = beds
        apt.bathrooms = baths
        apt.size_sqft = extract_sqft(detail_text)

    # Address / neighborhood
    addr_el = soup.select_one("[data-testid='listing-address'], .BuildingInfo-address")
    if addr_el:
        apt.full_address = clean_text(addr_el.get_text())

    nbhd_el = soup.select_one("[data-testid='neighborhood'], .Breadcrumb a")
    if nbhd_el:
        apt.neighborhood = clean_text(nbhd_el.get_text())

    apt.borough = detect_borough(apt.full_address or apt.neighborhood or "")

    # Available date
    avail_el = soup.find(string=re.compile(r"available", re.I))
    if avail_el:
        apt.availability_note = clean_text(str(avail_el))

    # Floor
    apt.floor = extract_floor(soup.get_text())

    # Building type
    btype_text = soup.get_text().lower()
    if "condo"      in btype_text: apt.building_type = BuildingTypeEnum.condo
    elif "co-op"    in btype_text: apt.building_type = BuildingTypeEnum.coop
    elif "townhouse" in btype_text: apt.building_type = BuildingTypeEnum.townhouse
    else:                           apt.building_type = BuildingTypeEnum.rental

    # No-fee / broker fee
    page_text = soup.get_text(" ")
    apt.no_fee     = bool(re.search(r"no\s+fee",          page_text, re.I))
    apt.broker_fee = bool(re.search(r"broker\s+fee",      page_text, re.I))
    apt.pets_allowed = bool(re.search(r"pets?\s+ok|pet\s+friendly", page_text, re.I))

    # Subway lines
    lines = extract_subway_lines(page_text)
    if lines:
        apt.subway_lines = lines

    # Amenities list
    amenities = []
    for el in soup.select(".Amenities li, [data-testid='amenity'], .amenity-item"):
        t = clean_text(el.get_text())
        if t:
            amenities.append(t)
    apt.amenities_raw = amenities or None

    # Laundry
    amenity_text = " ".join(amenities).lower()
    if "in-unit laundry" in amenity_text or "washer/dryer" in amenity_text:
        apt.laundry = "in_unit"
    elif "laundry" in amenity_text:
        apt.laundry = "building"

    # Utilities
    utils_match = re.search(r"(heat|hot water|electric|gas)[^\n]{0,60}included", page_text, re.I)
    if utils_match:
        apt.utilities_included = utils_match.group(0)[:100]

    # Lease term
    lease_m = re.search(r"(\d+)\s*[-–]\s*month|month[-\s]to[-\s]month|annual lease", page_text, re.I)
    if lease_m:
        apt.lease_term = lease_m.group(0)

    # Description
    desc_el = soup.select_one(".about-the-listing, [data-testid='description'], .DescriptionBlock")
    if desc_el:
        apt.raw_description = clean_text(desc_el.get_text())

    # Images
    imgs = [img["src"] for img in soup.select("img[src*='cdn']") if img.get("src")]
    apt.image_urls = list(dict.fromkeys(imgs))[:20] or None

    # Date listed
    date_el = soup.find(string=re.compile(r"listed\s+on|days?\s+ago|posted", re.I))
    if date_el:
        apt.availability_note = (apt.availability_note or "") + " | " + clean_text(str(date_el))


def _parse_host(soup: BeautifulSoup, db) -> Optional[Host]:
    """Parse agent/broker details from the listing page."""
    # StreetEasy agent section
    agent_el = soup.select_one(".agent-info, [data-testid='agent-name'], .ContactForm-agentName")
    if not agent_el:
        return None

    name = clean_text(agent_el.get_text())
    if not name:
        return None

    # Phone
    phone_m = re.search(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", soup.get_text())
    phone   = phone_m.group(0) if phone_m else None

    # Email
    email_m = re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", soup.get_text(), re.I)
    email   = email_m.group(0) if email_m else None

    # Company
    company_el = soup.select_one(".agent-company, [data-testid='brokerage-name']")
    company    = clean_text(company_el.get_text()) if company_el else None

    # Look up existing host
    host = None
    if email:
        host = db.query(Host).filter_by(email=email).first()
    if not host and phone:
        host = db.query(Host).filter_by(phone=phone).first()
    if not host:
        host = db.query(Host).filter_by(name=name).first()

    if not host:
        host = Host(name=name, email=email, phone=phone, company_name=company)
        db.add(host)
        db.flush()
    else:
        # Update any new info
        if email   and not host.email:    host.email    = email
        if phone   and not host.phone:    host.phone    = phone
        if company and not host.company_name: host.company_name = company

    return host


# ---------------------------------------------------------------------------
# ZenRows HTTP helper
# ---------------------------------------------------------------------------

def _zenrows_fetch(url: str, js_render: bool = True) -> Optional[str]:
    """
    Fetch a URL via ZenRows.
    js_render=True  — costs 5 credits but handles React/JS pages.
    js_render=False — costs 1 credit, fine for static pages.
    """
    params = {
        "apikey":          settings.ZENROWS_API_KEY,
        "url":             url,
        "js_render":       "true" if js_render else "false",
        "premium_proxy":   "true",     # use rotating residential proxies
        "antibot":         "true",     # enable anti-bot bypass
    }
    try:
        resp = requests.get(ZENROWS_API, params=params, timeout=60)
        if resp.status_code == 200:
            return resp.text
        logger.warning("ZenRows HTTP %d for %s: %s", resp.status_code, url, resp.text[:200])
    except requests.RequestException as exc:
        logger.error("ZenRows request failed for %s: %s", url, exc)
    return None