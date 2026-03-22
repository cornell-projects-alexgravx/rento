"""
SQLAlchemy ORM models for the Apartment Search Agent.
Tables: apartments, hosts, scrape_runs, raw_listings
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, ARRAY, JSON, Enum as SAEnum,
    UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceEnum(str, enum.Enum):
    craigslist = "craigslist"
    streeteasy  = "streeteasy"
    streeteasy_email = "streeteasy_email"

class StatusEnum(str, enum.Enum):
    active  = "active"
    expired = "expired"
    rented  = "rented"
    unknown = "unknown"

class BuildingTypeEnum(str, enum.Enum):
    condo     = "condo"
    coop      = "co-op"
    rental    = "rental"
    townhouse = "townhouse"
    unknown   = "unknown"

class LaundryEnum(str, enum.Enum):
    in_unit  = "in_unit"
    building = "building"
    none     = "none"
    unknown  = "unknown"

class HostTypeEnum(str, enum.Enum):
    owner      = "owner"
    broker     = "broker"
    management = "management_company"
    unknown    = "unknown"


# ---------------------------------------------------------------------------
# Host
# ---------------------------------------------------------------------------

class Host(Base):
    __tablename__ = "hosts"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(255))
    email            = Column(String(255))
    phone            = Column(String(50))
    host_type        = Column(SAEnum(HostTypeEnum), default=HostTypeEnum.unknown)
    company_name     = Column(String(255))
    website          = Column(String(512))

    # Trust / meta
    verified         = Column(Boolean, default=False)
    response_rate    = Column(Float)            # 0.0 – 1.0
    listings_count   = Column(Integer, default=0)
    scam_flag        = Column(Boolean, default=False)
    scam_reason      = Column(Text)

    # Timestamps
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    apartments       = relationship("Apartment", back_populates="host")

    __table_args__ = (
        UniqueConstraint("email", "phone", name="uq_host_email_phone"),
    )

    def __repr__(self):
        return f"<Host id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Apartment
# ---------------------------------------------------------------------------

class Apartment(Base):
    __tablename__ = "apartments"

    id               = Column(Integer, primary_key=True, autoincrement=True)

    # --- Source / dedup ---
    source           = Column(SAEnum(SourceEnum), nullable=False)
    source_url       = Column(String(1024))
    listing_id       = Column(String(255))          # source-native ID
    duplicate_of     = Column(Integer, ForeignKey("apartments.id"), nullable=True)

    # --- Location ---
    full_address     = Column(String(512))
    neighborhood     = Column(String(255))
    borough          = Column(String(100))          # Manhattan, Brooklyn, etc.
    city             = Column(String(100), default="New York")
    state            = Column(String(10),  default="NY")
    zip_code         = Column(String(10))
    lat              = Column(Float)
    lng              = Column(Float)
    floor            = Column(Integer)
    building_type    = Column(SAEnum(BuildingTypeEnum), default=BuildingTypeEnum.unknown)

    # --- Pricing ---
    price            = Column(Float)                # monthly rent USD
    price_per_sqft   = Column(Float)
    broker_fee       = Column(Boolean, default=False)
    no_fee           = Column(Boolean, default=False)
    deposit          = Column(Float)

    # --- Unit details ---
    bedrooms         = Column(Float)                # 0 = studio, 0.5 = junior 1BR
    bathrooms        = Column(Float)
    size_sqft        = Column(Float)
    rooms_total      = Column(Integer)

    # --- Availability ---
    available_date   = Column(DateTime)
    availability_note= Column(String(255))          # "immediately", "flex", etc.
    visit_days       = Column(String(255))           # free text or JSON array
    lease_term       = Column(String(100))           # "12 months", "month-to-month"
    min_lease_months = Column(Integer)

    # --- Amenities (structured) ---
    pets_allowed     = Column(Boolean)
    pets_note        = Column(String(255))           # "cats only", "small dogs"
    laundry          = Column(SAEnum(LaundryEnum), default=LaundryEnum.unknown)
    dishwasher       = Column(Boolean)
    doorman          = Column(Boolean)
    elevator         = Column(Boolean)
    gym              = Column(Boolean)
    roof_deck        = Column(Boolean)
    outdoor_space    = Column(String(100))           # terrace/yard/balcony/none
    parking          = Column(Boolean)
    parking_note     = Column(String(255))
    storage          = Column(Boolean)
    ac               = Column(Boolean)               # air conditioning
    heat_included    = Column(Boolean)
    utilities_included = Column(String(255))         # "heat+hot water", etc.
    subway_lines     = Column(ARRAY(String))         # ["A","C","E"]
    subway_distance_ft = Column(Float)

    # --- Rich text ---
    title            = Column(String(512))
    raw_description  = Column(Text)
    image_urls       = Column(ARRAY(String))
    amenities_raw    = Column(ARRAY(String))         # original amenity tags

    # --- AI enrichment ---
    ai_summary       = Column(Text)
    ai_score         = Column(Float)                 # 0–10 desirability score
    ai_flags         = Column(ARRAY(String))         # ["scam_risk","price_high"]
    ai_notes         = Column(Text)

    # --- Reviewer / story (user-side, for future UI) ---
    review           = Column(Text)
    story            = Column(Text)                  # "why this listing stood out"

    # --- Status / lifecycle ---
    status           = Column(SAEnum(StatusEnum), default=StatusEnum.active)
    date_listed      = Column(DateTime)
    date_scraped     = Column(DateTime, default=datetime.utcnow)
    date_updated     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    date_expired     = Column(DateTime)

    # --- Foreign keys ---
    host_id          = Column(Integer, ForeignKey("hosts.id"))
    scrape_run_id    = Column(Integer, ForeignKey("scrape_runs.id"))

    # --- Relationships ---
    host             = relationship("Host", back_populates="apartments")
    scrape_run       = relationship("ScrapeRun", back_populates="apartments")

    __table_args__ = (
        UniqueConstraint("source", "listing_id", name="uq_source_listing"),
        Index("ix_apt_price",    "price"),
        Index("ix_apt_beds",     "bedrooms"),
        Index("ix_apt_borough",  "borough"),
        Index("ix_apt_status",   "status"),
        Index("ix_apt_scraped",  "date_scraped"),
    )

    def __repr__(self):
        return f"<Apartment id={self.id} source={self.source} price={self.price}>"


# ---------------------------------------------------------------------------
# Scrape Run  (audit trail for every cron execution)
# ---------------------------------------------------------------------------

class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    source           = Column(SAEnum(SourceEnum), nullable=False)
    started_at       = Column(DateTime, default=datetime.utcnow)
    finished_at      = Column(DateTime)
    status           = Column(String(50), default="running")  # running/success/error
    listings_found   = Column(Integer, default=0)
    listings_new     = Column(Integer, default=0)
    listings_updated = Column(Integer, default=0)
    error_message    = Column(Text)
    meta             = Column(JSON)                 # extra info (URL params, etc.)

    apartments       = relationship("Apartment", back_populates="scrape_run")

    def __repr__(self):
        return f"<ScrapeRun id={self.id} source={self.source} status={self.status}>"


# ---------------------------------------------------------------------------
# Raw Listings  (immutable archive of everything fetched before parsing)
# ---------------------------------------------------------------------------

class RawListing(Base):
    __tablename__ = "raw_listings"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    source           = Column(SAEnum(SourceEnum), nullable=False)
    scrape_run_id    = Column(Integer, ForeignKey("scrape_runs.id"))
    raw_content      = Column(Text)                 # full XML/HTML/email body
    content_type     = Column(String(50))           # "rss_entry","html","email"
    url              = Column(String(1024))
    fetched_at       = Column(DateTime, default=datetime.utcnow)
    parsed           = Column(Boolean, default=False)
    apartment_id     = Column(Integer, ForeignKey("apartments.id"), nullable=True)

    def __repr__(self):
        return f"<RawListing id={self.id} source={self.source} parsed={self.parsed}>"