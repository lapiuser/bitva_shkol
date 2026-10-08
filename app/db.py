from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import ABOUT_TEXT, AUTHOR_WORDS, DONATION_URL, DATABASE_URL
from .schools import SCHOOLS, TYPE_TO_CATEGORY, CATEGORY_LABELS

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "institutions.csv"

AUTOINC_ID = BigInteger().with_variant(Integer, "sqlite")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
if DATABASE_URL.startswith("postgres"):
    engine = create_engine(
        DATABASE_URL,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
        pool_size=10,
        max_overflow=20,
    )
else:
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9№]+", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def school_key(city: str, category: str, name: str) -> str:
    return f"{normalize_name(city)}|{category}|{normalize_name(name)}"


def school_id(city: str, category: str, name: str) -> str:
    raw = school_key(city, category, name).encode("utf-8")
    return "ru_" + hashlib.sha256(raw).hexdigest()[:28]


class Base(DeclarativeBase):
    pass


class School(Base):
    __tablename__ = "schools"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    country: Mapped[str] = mapped_column(String(80), default="Россия", nullable=False)
    region: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    category_label: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    folder: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(600), nullable=False)
    image_source: Mapped[str] = mapped_column(String(20), default="placeholder", nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="national", nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    real_clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    artificial_clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("normalized_key", name="uq_school_normalized_key"),
        Index("ix_schools_city_category", "city", "category"),
        Index("ix_schools_rank", "real_clicks", "id"),
    )


class VisitorIdentity(Base):
    __tablename__ = "visitor_identities"
    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    ip_prefix: Mapped[str] = mapped_column(String(128), index=True)
    user_agent_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DailyVisitor(Base):
    __tablename__ = "daily_visitors"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    __table_args__ = (Index("ix_daily_visitors_day_seen", "day", "last_seen"),)


class VoterUsage(Base):
    __tablename__ = "voter_usage"
    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_click_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    captcha_verified_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UsedRequest(Base):
    __tablename__ = "used_requests"
    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    ip_prefix: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class IpDailyUsage(Base):
    __tablename__ = "ip_daily_usage"
    ip_prefix: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ClickEvent(Base):
    __tablename__ = "click_events"
    id: Mapped[int] = mapped_column(AUTOINC_ID, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    school_id: Mapped[str] = mapped_column(String(100), index=True)
    identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    taps: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    __table_args__ = (Index("ix_click_events_identity_time", "identity_hash", "created_at"),)


class AccountClickEvent(Base):
    __tablename__ = "account_click_events"
    id: Mapped[int] = mapped_column(AUTOINC_ID, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (Index("ix_account_click_events_account_time", "account_id", "created_at"),)


class AbuseEvent(Base):
    __tablename__ = "abuse_events"
    id: Mapped[int] = mapped_column(AUTOINC_ID, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    identity_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    ip_prefix: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class BlockedIdentity(Base):
    __tablename__ = "blocked_identities"
    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ip_prefix: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SiteCountry(Base):
    __tablename__ = "site_countries"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    telegram_username: Mapped[str] = mapped_column(String(80), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_subscriber: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_subscription_check: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class TelegramVerificationCode(Base):
    __tablename__ = "telegram_verification_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    tg_user_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    telegram_username: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BroadcastNotice(Base):
    __tablename__ = "broadcast_notices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String(240), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    author: Mapped[str] = mapped_column(String(80), default="admin", nullable=False)


class SiteSetting(Base):
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AccountSchoolClick(Base):
    __tablename__ = "account_school_clicks"
    account_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    __table_args__ = (Index("ix_account_school_clicks_school", "school_id"),)


class TelegramVerificationChallenge(Base):
    __tablename__ = "telegram_verification_challenges"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_username: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    tg_user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PhotoSubmission(Base):
    __tablename__ = "photo_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    consent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(30), default="2026-10-07", nullable=False)
    submitter_identity: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    submitter_account_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GlobalGameEvent(Base):
    __tablename__ = "global_game_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    music_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


def seed_legacy_kaliningrad(db) -> int:
    """Keep the 75 legacy Kaliningrad entries, but intentionally ship no school photos."""
    added = 0
    for spec in SCHOOLS:
        key = school_key(spec.city, spec.category, spec.name)
        existing = db.scalar(select(School).where(School.normalized_key == key))
        if existing:
            # Never overwrite a photo uploaded by the administrator on restart.
            if existing.image_source != "upload":
                existing.image_source = "placeholder"
            existing.origin = "legacy"
            existing.folder = f"legacy/{spec.id}"
            continue
        db.add(
            School(
                id=spec.id,
                country=spec.country,
                region=spec.region,
                city=spec.city,
                category=spec.category,
                category_label=spec.category_label,
                name=spec.name,
                folder=f"legacy/{spec.id}",
                normalized_key=key,
                image_source="placeholder",
                origin="legacy",
                is_active=1,
                real_clicks=0,
                artificial_clicks=0,
            )
        )
        added += 1
    if added:
        db.flush()
    return added


def import_national_csv(db) -> int:
    if not CSV_PATH.exists():
        return 0
    added = 0
    existing_keys = set(db.scalars(select(School.normalized_key)).all())
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = (row.get("city") or "").strip()
            name = (row.get("name") or "").strip()
            type_code = (row.get("type_code") or "").strip().lower()
            country = (row.get("country") or "Россия").strip() or "Россия"
            category = TYPE_TO_CATEGORY.get(type_code)
            if not city or not name or not category:
                continue
            if normalize_name(city) == normalize_name("Калининград"):
                continue
            key = school_key(city, category, name)
            if key in existing_keys:
                continue
            sid = school_id(city, category, name)
            db.add(
                School(
                    id=sid,
                    country=country,
                    region=None,
                    city=city,
                    category=category,
                    category_label=CATEGORY_LABELS[category],
                    name=name,
                    folder=f"national/{sid}",
                    normalized_key=key,
                    image_source="placeholder",
                    origin="national",
                    is_active=1,
                    real_clicks=0,
                    artificial_clicks=0,
                )
            )
            existing_keys.add(key)
            added += 1
    if added:
        db.flush()
    return added


def ensure_schema_compatibility() -> None:
    """Add small additive columns needed by newer releases without resetting data."""
    with engine.begin() as conn:
        try:
            cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(click_events)").fetchall()} if engine.dialect.name == "sqlite" else {row[0] for row in conn.exec_driver_sql("SELECT column_name FROM information_schema.columns WHERE table_name='click_events'").fetchall()}
            if "taps" not in cols:
                conn.exec_driver_sql("ALTER TABLE click_events ADD COLUMN taps INTEGER NOT NULL DEFAULT 0")
            conn.exec_driver_sql("UPDATE click_events SET taps = clicks WHERE taps = 0")
        except Exception as exc:
            print(f"[startup] schema compatibility step skipped: {exc}", flush=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    with SessionLocal() as db:
        defaults = {
            "about_text": ABOUT_TEXT,
            "author_words": AUTHOR_WORDS,
            "donation_url": DONATION_URL,
        }
        for key, value in defaults.items():
            if db.get(SiteSetting, key) is None:
                db.add(SiteSetting(key=key, value=str(value or ""), updated_at=utcnow()))
        legacy_added = seed_legacy_kaliningrad(db)
        national_added = import_national_csv(db)
        country_names = {"Россия"}
        for country in db.scalars(select(School.country).distinct()).all():
            if country:
                country_names.add(str(country).strip())
        for country_name in sorted(country_names, key=lambda x: (0 if x == "Россия" else 1, x.casefold())):
            if db.get(SiteCountry, country_name) is None:
                db.add(SiteCountry(name=country_name, is_active=1, sort_order=0 if country_name == "Россия" else 100, created_at=utcnow()))
        db.commit()
        total = db.scalar(select(func.count(School.id))) or 0
        source_count = 0
        if CSV_PATH.exists():
            with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
                source_count = max(0, sum(1 for _ in f) - 1)
        print(
            f"[startup] schools={total} legacy_kaliningrad={len(SCHOOLS)} source_rows={source_count} "
            f"legacy_added={legacy_added} national_added={national_added}",
            flush=True,
        )
