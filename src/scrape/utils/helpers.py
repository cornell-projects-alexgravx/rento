"""
Shared utility functions used across scrapers and parsers.
"""

import re
import hashlib
import logging
import time
from typing import Optional, Tuple, List
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean_text(text: Optional[str]) -> Optional[str]:
    """Strip HTML tags, collapse whitespace, return None for empty strings."""
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def extract_price(text: str) -> Optional[float]:
    """Pull the first dollar amount from a string.  '$3,500/mo' → 3500.0"""
    if not text:
        return None
    match = re.search(r"\$[\d,]+", text)
    if match:
        return float(match.group().replace("$", "").replace(",", ""))
    return None


def extract_beds_baths(text: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Try to parse 'X bed / Y bath' variants.
    Returns (beds, baths) as floats; None if not found.
    """
    beds = baths = None
    bed_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:br|bed|bedroom)", text, re.I)
    bath_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:ba|bath|bathroom)", text, re.I)
    if bed_m:
        beds = float(bed_m.group(1))
    if bath_m:
        baths = float(bath_m.group(1))
    return beds, baths


def extract_sqft(text: str) -> Optional[float]:
    """'1,200 sq ft' or '1200sqft' → 1200.0"""
    if not text:
        return None
    match = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|sqft|square feet)", text, re.I)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def extract_floor(text: str) -> Optional[int]:
    """'3rd floor', 'floor 4', 'FL5' → int"""
    if not text:
        return None
    match = re.search(r"(?:floor\s*|fl\.?\s*)(\d+)|(\d+)(?:st|nd|rd|th)?\s*floor", text, re.I)
    if match:
        return int(match.group(1) or match.group(2))
    return None


def extract_subway_lines(text: str) -> List[str]:
    """Find NYC subway line letters/numbers in text.  'Near the A, C, E' → ['A','C','E']"""
    if not text:
        return []
    valid = set("123456ABCDEFGJLMNQRSWZ")
    found = re.findall(r"\b([1-6ABCDEFGJLMNQRSWZ])\b", text)
    return sorted(set(f for f in found if f in valid))


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def listing_fingerprint(source: str, listing_id: str) -> str:
    """Stable fingerprint for (source, listing_id) — used as a dedup key."""
    raw = f"{source}::{listing_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def url_to_listing_id(url: str) -> str:
    """Extract a stable ID from a listing URL (last path segment)."""
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] or hashlib.md5(url.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Geocoding  (Nominatim — free, no key needed, rate-limited to 1 req/s)
# ---------------------------------------------------------------------------

_NOMINATIM = "https://nominatim.openstreetmap.org/search"

def geocode_address(address: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Geocode a NYC address string via OSM Nominatim.
    Returns (lat, lng) or (None, None) on failure.
    """
    try:
        resp = requests.get(
            _NOMINATIM,
            params={"q": address + ", New York City, NY", "format": "json", "limit": 1},
            headers={"User-Agent": "AptSearchAgent/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.debug("Geocode failed for %r: %s", address, exc)
    time.sleep(1)          # Nominatim rate limit: 1 req/s
    return None, None


# ---------------------------------------------------------------------------
# Borough detection
# ---------------------------------------------------------------------------

_BOROUGH_MAP = {
    "manhattan": "Manhattan",
    "brooklyn":  "Brooklyn",
    "queens":    "Queens",
    "bronx":     "Bronx",
    "staten island": "Staten Island",
    # Craigslist sub-areas
    "mnh": "Manhattan",
    "brk": "Brooklyn",
    "que": "Queens",
    "brx": "Bronx",
    "stn": "Staten Island",
}

def detect_borough(text: str) -> Optional[str]:
    if not text:
        return None
    low = text.lower()
    for key, val in _BOROUGH_MAP.items():
        if key in low:
            return val
    return None