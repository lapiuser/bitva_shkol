from __future__ import annotations

import hashlib
import hmac
import os
import ipaddress
import json
import re
import secrets
import ssl
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request as URLRequest, urlopen

import certifi

from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from . import bot as telegram_bot
from .config import (
    ABOUT_TEXT, ACCOUNT_SESSION_DAYS, ACTIVE_USER_SECONDS, ADMIN_PASSWORD, ADMIN_SESSION_HOURS, BOT_CODE_MINUTES,
    ADMIN_USERNAME, ACTOR_BURST_LIMIT_5S, ACTOR_CLICK_LIMIT_PER_MINUTE, CAPTCHA_SESSION_MINUTES,
    CLICK_BURST_LIMIT_5S, CLICK_LIMIT_PER_MINUTE, CLICK_MAX_PER_REQUEST, COOKIE_SECURE,
    DONATION_URL, EVENT_RETENTION_SECONDS, IP_DAILY_CLICK_LIMIT, IP_REQUEST_LIMIT_PER_MINUTE,
    MAX_NOTICE_CHARS, MAX_UPLOAD_MB, MAX_EVENT_AUDIO_MB, GAME_EVENT_SECONDS, RATING_REFRESH_SECONDS, SECRET_KEY, STATS_REFRESH_SECONDS,
    TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_URL, TELEGRAM_CHANNEL_USERNAME, TURNSTILE_ENABLED, TURNSTILE_MODE, SITE_PUBLIC_URL, DATABASE_URL,
    TURNSTILE_SECRET_KEY, TURNSTILE_SITE_KEY, VERIFIED_MULTIPLIER, SUBSCRIPTION_REFRESH_MINUTES, AUTHOR_WORDS, TELEGRAM_SSL_VERIFY, TELEGRAM_CA_FILE,
)
from .db import (
    AbuseEvent, Account, AccountClickEvent, AccountSchoolClick, AdminSession, BlockedIdentity, BroadcastNotice, ClickEvent, DailyVisitor,
    GlobalGameEvent, IpDailyUsage, PhotoSubmission, School, SessionLocal, SiteCountry, SiteSetting, TelegramVerificationChallenge, TelegramVerificationCode,
    UserSession, UsedRequest, VisitorIdentity, VoterUsage, init_db, school_id, school_key, utcnow,
)
from .schools import CATEGORY_LABELS, CATEGORY_ORDER, SCHOOLS, TYPE_TO_CATEGORY, asset_paths

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "schools"
EVENT_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "events"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EVENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CLICK_COOKIE = "bitva_device"
ADMIN_COOKIE = "bitva_admin"
USER_COOKIE = "bitva_user"
SECRET_KEY_BYTES = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()


def today_key() -> str:
    return utcnow().strftime("%Y-%m-%d")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_text(value: str, max_len: int) -> str:
    return " ".join(str(value or "").strip().split())[:max_len]


def client_ip(request: Request) -> str:
    for header in ("CF-Connecting-IP", "X-Real-IP"):
        value = request.headers.get(header, "").strip()
        if value:
            return value
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def ip_prefix(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
        if addr.version == 4:
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
            return f"{net.network_address}/24"
        net = ipaddress.ip_network(f"{ip}/64", strict=False)
        return f"{net.network_address}/64"
    except ValueError:
        return ip[:120]


def user_session_account(db, token: str | None) -> Account | None:
    if not token:
        return None
    row = db.get(UserSession, hash_token(token))
    if not row or row.expires_at <= utcnow():
        return None
    return db.get(Account, row.account_id)


def account_from_request(request: Request) -> tuple[Account | None, str | None]:
    token = request.cookies.get(USER_COOKIE, "")
    with SessionLocal() as db:
        return user_session_account(db, token), token or None


def identity_from_request(request: Request, response: Response) -> tuple[str, str, str, str]:
    device_id = request.cookies.get(CLICK_COOKIE, "").strip()
    if not device_id or len(device_id) > 120:
        device_id = secrets.token_urlsafe(32)
        response.set_cookie(
            CLICK_COOKIE,
            device_id,
            max_age=31536000,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            path="/",
        )
    prefix = ip_prefix(client_ip(request))
    ua = clean_text(request.headers.get("user-agent", "unknown"), 300)
    ua_hash = hashlib.sha256(ua.encode("utf-8")).hexdigest()
    material = f"{device_id}|{prefix}|{ua_hash}"
    identity = hmac.new(SECRET_KEY_BYTES, material.encode("utf-8"), hashlib.sha256).hexdigest()
    return identity, prefix, ua_hash, device_id


def ensure_identity(request: Request, response: Response) -> tuple[str, str, str]:
    identity, prefix, ua_hash, _ = identity_from_request(request, response)
    now = utcnow()
    with SessionLocal() as db:
        row = db.get(VisitorIdentity, identity)
        if row is None:
            db.add(VisitorIdentity(identity_hash=identity, ip_prefix=prefix, user_agent_hash=ua_hash, created_at=now, last_seen=now))
        else:
            row.ip_prefix = prefix
            row.user_agent_hash = ua_hash
            row.last_seen = now
        db.commit()
    return identity, prefix, ua_hash


def blocked(db, identity: str) -> bool:
    return db.get(BlockedIdentity, identity) is not None


def log_abuse(db, event_type: str, identity: str | None, prefix: str | None, details: str) -> None:
    cutoff = utcnow() - timedelta(seconds=60)
    q = db.query(AbuseEvent).filter(AbuseEvent.event_type == event_type, AbuseEvent.created_at >= cutoff)
    if identity:
        q = q.filter(AbuseEvent.identity_hash == identity)
    elif prefix:
        q = q.filter(AbuseEvent.ip_prefix == prefix)
    if q.first() is not None:
        return
    db.add(AbuseEvent(event_type=event_type, identity_hash=identity, ip_prefix=prefix, details=details[:1000], created_at=utcnow()))


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin", "").strip()
    if not origin:
        return
    try:
        if urlparse(origin).netloc != request.headers.get("host", ""):
            raise HTTPException(status_code=403, detail="Недопустимый источник запроса")
    except ValueError:
        raise HTTPException(status_code=403, detail="Недопустимый источник запроса")


def external_ssl_context():
    if not TELEGRAM_SSL_VERIFY:
        return False
    cafile = TELEGRAM_CA_FILE or certifi.where()
    try:
        return ssl.create_default_context(cafile=cafile)
    except Exception:
        return ssl.create_default_context()


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    if not TURNSTILE_ENABLED:
        return True
    if not TURNSTILE_SECRET_KEY or not token:
        return False
    payload = json.dumps({"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": remote_ip}).encode("utf-8")
    req = URLRequest(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=6, context=external_ssl_context()) as result:
            data = json.loads(result.read(8192).decode("utf-8"))
        return bool(data.get("success"))
    except Exception:
        return False



def ensure_usage(db, identity: str, now: datetime) -> VoterUsage:
    usage = db.get(VoterUsage, identity)
    day = today_key()
    if usage is None:
        usage = VoterUsage(identity_hash=identity, day=day, clicks=0)
        db.add(usage)
        db.flush()
    elif usage.day != day:
        usage.day = day
        usage.clicks = 0
        usage.last_click_at = None
        usage.captcha_verified_until = None
    return usage


def captcha_is_verified(db, identity: str, now: datetime) -> bool:
    usage = db.get(VoterUsage, identity)
    return bool(usage and usage.captcha_verified_until and usage.captcha_verified_until > now)


def recent_clicks_for_identity(db, identity: str, now: datetime, seconds: int) -> int:
    value = db.query(func.coalesce(func.sum(ClickEvent.taps), 0)).filter(
        ClickEvent.identity_hash == identity,
        ClickEvent.created_at >= now - timedelta(seconds=seconds),
    ).scalar() or 0
    return int(value)


def recent_clicks_for_actor(db, ip_prefix_value: str, ua_hash: str, now: datetime, seconds: int) -> int:
    value = db.query(func.coalesce(func.sum(ClickEvent.taps), 0)).join(
        VisitorIdentity, VisitorIdentity.identity_hash == ClickEvent.identity_hash
    ).filter(
        VisitorIdentity.ip_prefix == ip_prefix_value,
        VisitorIdentity.user_agent_hash == ua_hash,
        ClickEvent.created_at >= now - timedelta(seconds=seconds),
    ).scalar() or 0
    return int(value)


def recent_clicks_for_account(db, account_id: int, now: datetime, seconds: int) -> int:
    value = db.query(func.coalesce(func.sum(AccountClickEvent.clicks), 0)).filter(
        AccountClickEvent.account_id == account_id,
        AccountClickEvent.created_at >= now - timedelta(seconds=seconds),
    ).scalar() or 0
    return int(value)


def normalize_username(value: str) -> str:
    return clean_text(value, 80).lstrip("@").lower()


def password_hash(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return salt.hex(), digest.hex()


def password_ok(password: str, salt_hex: str, stored_hash: str) -> bool:
    _, candidate = password_hash(password, salt_hex)
    return hmac.compare_digest(candidate, stored_hash)


def effective_limits(account: Account | None) -> tuple[int, int, int, int]:
    multiplier = VERIFIED_MULTIPLIER if account and account.is_subscriber else 1
    minute_limit = CLICK_LIMIT_PER_MINUTE * multiplier
    burst_limit = CLICK_BURST_LIMIT_5S * multiplier
    actor_minute = ACTOR_CLICK_LIMIT_PER_MINUTE * multiplier
    actor_burst = ACTOR_BURST_LIMIT_5S * multiplier
    return minute_limit, burst_limit, actor_minute, actor_burst


def score_expr():
    return School.real_clicks + School.artificial_clicks


def setting_value(key: str, fallback: str = "") -> str:
    with SessionLocal() as db:
        row = db.get(SiteSetting, key)
        return row.value if row else fallback


def iso_utc(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


def bot_url() -> str:
    runtime_username = telegram_bot.BOT_USERNAME_RUNTIME.strip().lstrip("@") if telegram_bot.BOT_USERNAME_RUNTIME else ""
    env_username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if runtime_username:
        return f"https://t.me/{runtime_username}"
    configured = TELEGRAM_BOT_URL.strip()
    if configured:
        return configured
    return f"https://t.me/{env_username}" if env_username else ""


def school_payload(row: School, include_image: bool = True) -> dict:
    result = {
        "id": row.id,
        "name": row.name,
        "category": row.category,
        "category_label": row.category_label,
        "country": row.country,
        "region": row.region or "",
        "city": row.city,
    }
    result["clicks"] = int(row.real_clicks + row.artificial_clicks)
    if include_image:
        result["images"] = asset_paths(row)
    return result


class ClickPayload(BaseModel):
    school_id: str = Field(min_length=1, max_length=100)
    clicks: int = Field(ge=1, le=CLICK_LIMIT_PER_MINUTE * VERIFIED_MULTIPLIER)
    request_id: str = Field(min_length=16, max_length=80)


class HeartbeatPayload(BaseModel):
    school_id: str | None = None


class CaptchaPayload(BaseModel):
    token: str = Field(min_length=1, max_length=2048)


class AdminLoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
    captcha_token: str | None = Field(default=None, max_length=2048)


class BlockPayload(BaseModel):
    identity_hash: str = Field(min_length=32, max_length=64)
    reason: str = Field(default="", max_length=500)


class AccountRegisterPayload(BaseModel):
    telegram_username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    code: str = Field(min_length=8, max_length=16)


class AccountLoginPayload(BaseModel):
    telegram_username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class NoticePayload(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_NOTICE_CHARS)


class VerificationStartPayload(BaseModel):
    telegram_username: str = Field(min_length=2, max_length=80)


class VerificationStatusPayload(BaseModel):
    code: str = Field(min_length=8, max_length=16)


class SiteSettingsPayload(BaseModel):
    about_text: str = Field(min_length=1, max_length=5000)
    author_words: str = Field(min_length=1, max_length=5000)
    donation_url: str = Field(min_length=1, max_length=500)


class CountryPayload(BaseModel):
    name: str = Field(min_length=2, max_length=80)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await telegram_bot.start_bot()
    yield
    await telegram_bot.stop_bot()


app = FastAPI(title="БИТВА ШКОЛ", version="4.0.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/uploads/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response


@app.get("/api/config")
def public_config():
    return {
        "site_name": "БИТВА ШКОЛ",
        "captcha_enabled": TURNSTILE_ENABLED,
        "turnstile_site_key": TURNSTILE_SITE_KEY if TURNSTILE_ENABLED else "",
        "turnstile_mode": TURNSTILE_MODE,
        "donation_url": setting_value("donation_url", DONATION_URL),
        "stats_refresh_seconds": STATS_REFRESH_SECONDS,
        "rating_refresh_seconds": RATING_REFRESH_SECONDS,
        "click_limit_per_minute": CLICK_LIMIT_PER_MINUTE,
        "click_max_per_request": CLICK_LIMIT_PER_MINUTE * VERIFIED_MULTIPLIER,
        "verified_multiplier": VERIFIED_MULTIPLIER,
        "telegram_channel_url": f"https://t.me/{TELEGRAM_CHANNEL_USERNAME.lstrip('@')}",
        "telegram_bot_url": bot_url(),
        "storage": "mysql" if str(DATABASE_URL).startswith("mysql") else ("postgres" if not str(DATABASE_URL).startswith("sqlite") else "sqlite"),
        "countries_enabled": True,
    }


@app.get("/api/session")
def session(response: Response, request: Request):
    identity, prefix, ua_hash = ensure_identity(request, response)
    now = utcnow()
    with SessionLocal() as db:
        account = user_session_account(db, request.cookies.get(USER_COOKIE))
        minute_limit, _, _, _ = effective_limits(account)
        if blocked(db, identity):
            return {
                "ok": True, "visitor": identity[:12], "clicks_minute": 0, "remaining": 0,
                "limit_per_minute": minute_limit, "captcha_required": TURNSTILE_ENABLED,
                "account_authenticated": bool(account), "verified_subscriber": bool(account and account.is_subscriber),
                "multiplier": VERIFIED_MULTIPLIER if account and account.is_subscriber else 1,
            }
        row = db.query(DailyVisitor).filter(DailyVisitor.day == today_key(), DailyVisitor.identity_hash == identity).first()
        if row:
            row.last_seen = now
        else:
            db.add(DailyVisitor(day=today_key(), identity_hash=identity, last_seen=now))
        ensure_usage(db, identity, now)
        db.commit()
        clicks_minute = recent_clicks_for_identity(db, identity, now, 60)
        if account:
            stale = not account.last_subscription_check or account.last_subscription_check < now - timedelta(minutes=SUBSCRIPTION_REFRESH_MINUTES)
        else:
            stale = False
    if account and stale and TELEGRAM_BOT_TOKEN:
        try:
            import aiohttp
            async def refresh():
                from importlib import import_module
                async with aiohttp.ClientSession(**telegram_bot.telegram_session_kwargs()) as http:
                    return await telegram_bot.check_subscription(http, int(account.tg_user_id))
            # FastAPI sync endpoint is executed in a worker; use a tiny one-shot loop.
            import asyncio
            subscribed = asyncio.run(refresh())
            with SessionLocal() as db:
                live = db.get(Account, account.id)
                if live:
                    live.is_subscriber = 1 if subscribed else 0
                    live.last_subscription_check = utcnow()
                    db.commit()
                    account = live
        except Exception:
            pass
    minute_limit, _, _, _ = effective_limits(account)
    return {
        "ok": True,
        "visitor": identity[:12],
        "clicks_minute": clicks_minute,
        "remaining": max(0, minute_limit - clicks_minute),
        "limit_per_minute": minute_limit,
        "captcha_required": TURNSTILE_ENABLED,
        "account_authenticated": bool(account),
        "telegram_username": account.telegram_username if account else "",
        "verified_subscriber": bool(account and account.is_subscriber),
        "multiplier": VERIFIED_MULTIPLIER if account and account.is_subscriber else 1,
    }


@app.post("/api/captcha/verify")
def captcha_verify(payload: CaptchaPayload, request: Request, response: Response):
    require_same_origin(request)
    identity, prefix, _ = ensure_identity(request, response)
    now = utcnow()
    with SessionLocal() as db:
        if blocked(db, identity):
            raise HTTPException(status_code=403, detail="Доступ ограничен")
        if not verify_turnstile(payload.token, client_ip(request)):
            log_abuse(db, "invalid_captcha", identity, prefix, "Turnstile verification failed")
            db.commit()
            raise HTTPException(status_code=403, detail="Проверка не пройдена")
        usage = ensure_usage(db, identity, now)
        usage.captcha_verified_until = now + timedelta(minutes=CAPTCHA_SESSION_MINUTES)
        db.commit()
    return {"ok": True}


@app.get("/api/countries")
def countries():
    with SessionLocal() as db:
        country_rows = db.query(SiteCountry).filter(SiteCountry.is_active == 1).order_by(SiteCountry.sort_order.asc(), SiteCountry.name.asc()).all()
        if not any(r.name == "Россия" for r in country_rows):
            ru = db.get(SiteCountry, "Россия")
            if ru is None:
                ru = SiteCountry(name="Россия", is_active=1, sort_order=0, created_at=utcnow()); db.add(ru); db.flush()
            else:
                ru.is_active = 1; ru.sort_order = 0
            country_rows = [ru] + country_rows
        items = []
        for country in country_rows:
            school_count = db.query(func.count(School.id)).filter(School.is_active == 1, School.country == country.name).scalar() or 0
            city_count = db.query(func.count(func.distinct(School.city))).filter(School.is_active == 1, School.country == country.name).scalar() or 0
            items.append({"name": country.name, "school_count": int(school_count), "city_count": int(city_count)})
        return {"countries": items}


@app.get("/api/cities")
def cities(country: str = "Россия"):
    country = clean_text(country, 80) or "Россия"
    with SessionLocal() as db:
        rows = db.query(School.city, func.count(School.id)).filter(School.is_active == 1, School.country == country).group_by(School.city).order_by(School.city.asc()).all()
        return {"country": country, "cities": [{"name": city, "count": int(count)} for city, count in rows]}


@app.get("/api/cities/{city}/categories")
def city_categories(city: str, country: str = "Россия"):
    city = clean_text(city, 160)
    country = clean_text(country, 80) or "Россия"
    with SessionLocal() as db:
        rows = db.query(School).filter(School.is_active == 1, School.country == country, School.city == city).order_by(School.category.asc(), School.name.asc()).all()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row.category, []).append(school_payload(row, include_image=False))
        categories = [{"id": key, "name": CATEGORY_LABELS.get(key, key), "schools": grouped[key]} for key in CATEGORY_ORDER if key in grouped]
        if not categories:
            raise HTTPException(status_code=404, detail="Город не найден")
        return {"country": country, "city": city, "categories": categories}


@app.get("/api/schools/{school_id}")
def school_detail(school_id: str):
    with SessionLocal() as db:
        row = db.get(School, school_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Учебное заведение не найдено")
        return school_payload(row, include_image=True)


@app.get("/api/leaderboard")
def leaderboard(school_id: str | None = None, city: str | None = None, limit: int = 100, scope: str = "schools"):
    limit = max(10, min(int(limit), 100))
    scope = (scope or "schools").strip().lower()
    if scope not in {"schools", "cities", "city_schools"}:
        scope = "schools"
    with SessionLocal() as db:
        if scope == "city_schools":
            target_city = clean_text(city or "", 160)
            if not target_city and school_id:
                target = db.get(School, school_id)
                target_city = target.city if target else ""
            if not target_city:
                return {"scope": "city_schools", "items": [], "mine": None, "city": ""}
            rows = db.query(School).filter(School.is_active == 1, School.city == target_city).order_by(score_expr().desc(), School.id.asc()).limit(limit).all()
            items = [{"rank": idx, "id": row.id, "name": row.name, "city": row.city, "region": row.region or "Россия", "clicks": int(row.real_clicks + row.artificial_clicks), "kind": "school"} for idx, row in enumerate(rows, start=1)]
            mine = None
            if school_id:
                target = db.get(School, school_id)
                if target and target.is_active and target.city == target_city:
                    better = db.query(func.count(School.id)).filter(School.is_active == 1, School.city == target_city, score_expr() > (target.real_clicks + target.artificial_clicks)).scalar() or 0
                    same_before = db.query(func.count(School.id)).filter(School.is_active == 1, School.city == target_city, score_expr() == (target.real_clicks + target.artificial_clicks), School.id < target.id).scalar() or 0
                    mine = {"rank": int(better + same_before + 1), "id": target.id, "name": target.name, "city": target.city, "region": target.region or "Россия", "clicks": int(target.real_clicks + target.artificial_clicks), "kind": "school"}
            return {"scope": "city_schools", "items": items, "mine": mine, "city": target_city}

        if scope == "cities":
            rows = db.query(
                School.city.label("city"),
                func.coalesce(func.sum(score_expr()), 0).label("clicks"),
                func.count(School.id).label("school_count"),
            ).filter(School.is_active == 1).group_by(School.city).order_by(text("clicks DESC"), School.city.asc()).limit(limit).all()
            items = [{
                "rank": idx, "id": f"city:{row.city}", "name": row.city, "city": row.city, "region": "Россия",
                "clicks": int(row.clicks or 0), "school_count": int(row.school_count or 0), "kind": "city",
            } for idx, row in enumerate(rows, start=1)]
            mine = None
            if school_id:
                target = db.get(School, school_id)
                if target and target.is_active:
                    city_sums = db.query(
                        School.city,
                        func.coalesce(func.sum(score_expr()), 0).label("clicks"),
                    ).filter(School.is_active == 1).group_by(School.city).all()
                    city_total = next((int(v or 0) for city, v in city_sums if city == target.city), 0)
                    rank = 1 + sum(1 for city, value in city_sums if int(value or 0) > city_total or (int(value or 0) == city_total and str(city) < str(target.city)))
                    school_count = db.query(func.count(School.id)).filter(School.is_active == 1, School.city == target.city).scalar() or 0
                    mine = {"rank": int(rank), "id": f"city:{target.city}", "name": target.city, "city": target.city, "region": "Россия", "clicks": city_total, "school_count": int(school_count), "kind": "city"}
            return {"scope": "cities", "items": items, "mine": mine}

        rows = db.query(School).filter(School.is_active == 1).order_by(score_expr().desc(), School.id.asc()).limit(limit).all()
        items = [{"rank": idx, "id": row.id, "name": row.name, "city": row.city, "region": row.region or "Россия", "clicks": int(row.real_clicks + row.artificial_clicks), "kind": "school"} for idx, row in enumerate(rows, start=1)]
        mine = None
        if school_id:
            target = db.get(School, school_id)
            if target and target.is_active:
                better = db.query(func.count(School.id)).filter(School.is_active == 1, score_expr() > (target.real_clicks + target.artificial_clicks)).scalar() or 0
                same_before = db.query(func.count(School.id)).filter(School.is_active == 1, score_expr() == (target.real_clicks + target.artificial_clicks), School.id < target.id).scalar() or 0
                mine = {"rank": int(better + same_before + 1), "id": target.id, "name": target.name, "city": target.city, "region": target.region or "Россия", "clicks": int(target.real_clicks + target.artificial_clicks), "kind": "school"}
        return {"scope": "schools", "items": items, "mine": mine}


@app.get("/api/stats")
def stats():
    now = utcnow()
    cutoff = now - timedelta(seconds=ACTIVE_USER_SECONDS)
    epoch = int(now.replace(tzinfo=timezone.utc).timestamp())
    points = list(range(epoch - 9, epoch + 1))
    with SessionLocal() as db:
        total_visitors = db.query(func.count(VisitorIdentity.identity_hash)).scalar() or 0
        active_users = db.query(func.count(VisitorIdentity.identity_hash)).filter(VisitorIdentity.last_seen >= cutoff).scalar() or 0
        total = db.query(func.coalesce(func.sum(score_expr()), 0)).filter(School.is_active == 1).scalar() or 0
        schools_playing = db.query(func.count(School.id)).filter(School.is_active == 1, score_expr() > 0).scalar() or 0
        recent = db.query(ClickEvent).filter(ClickEvent.created_at >= now - timedelta(seconds=12)).all()
    bucket = {x: 0 for x in points}
    for event in recent:
        sec = int(event.created_at.replace(tzinfo=timezone.utc).timestamp())
        if sec in bucket:
            bucket[sec] += int(event.clicks)
    values = [bucket[x] for x in points]
    return {
        "total_visitors": int(total_visitors),
        "active_users": int(active_users),
        "total_clicks": int(total),
        "schools_playing": int(schools_playing),
        "cps_current": int(values[-1]),
        "cps_avg_10s": round(sum(values) / 10, 1),
        "cps_last_10_seconds": values,
        "click_limit_per_minute": CLICK_LIMIT_PER_MINUTE,
    }


@app.get("/api/about")
def about():
    return {
        "title": "О проекте",
        "text": setting_value("about_text", ""),
        "author_title": "СЛОВА АВТОРА",
        "author_words": setting_value("author_words", AUTHOR_WORDS),
        "production": "Anton Ljungberg Production",
        "donation_url": setting_value("donation_url", DONATION_URL),
        "contact_url": "https://t.me/lapiduser",
        "contact_text": "Добавить фото школы",
    }


@app.get("/api/notice")
def notice():
    now = utcnow()
    with SessionLocal() as db:
        row = db.query(BroadcastNotice).filter(BroadcastNotice.expires_at > now).order_by(BroadcastNotice.id.desc()).first()
        if not row:
            return {"active": False}
        return {"active": True, "id": row.id, "text": row.text, "created_at": iso_utc(row.created_at), "expires_at": iso_utc(row.expires_at)}


@app.post("/api/heartbeat")
def heartbeat(payload: HeartbeatPayload, request: Request, response: Response):
    require_same_origin(request)
    identity, prefix, ua_hash = ensure_identity(request, response)
    now = utcnow()
    with SessionLocal() as db:
        if blocked(db, identity):
            return {"ok": False}
        row = db.query(DailyVisitor).filter(DailyVisitor.day == today_key(), DailyVisitor.identity_hash == identity).first()
        if row:
            row.last_seen = now
        else:
            db.add(DailyVisitor(day=today_key(), identity_hash=identity, last_seen=now))
        visitor = db.get(VisitorIdentity, identity)
        if visitor:
            visitor.last_seen = now
            visitor.ip_prefix = prefix
            visitor.user_agent_hash = ua_hash
        db.commit()
    return {"ok": True}


@app.post("/api/clicks")
def clicks(payload: ClickPayload, request: Request, response: Response):
    require_same_origin(request)
    identity, prefix, ua_hash = ensure_identity(request, response)
    now = utcnow()
    current_ua_hash = hashlib.sha256(clean_text(request.headers.get("user-agent", "unknown"), 300).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(ua_hash, current_ua_hash):
        raise HTTPException(status_code=403, detail="Проверка запроса не пройдена")
    suspicious_ua = any(x in request.headers.get("user-agent", "").lower() for x in ("curl/", "python-requests", "wget/", "scrapy/", "httpclient"))

    with SessionLocal() as db:
        account = user_session_account(db, request.cookies.get(USER_COOKIE))
        if account is not None:
            account = db.execute(select(Account).where(Account.id == account.id).with_for_update()).scalar_one_or_none()
        minute_limit, burst_limit, actor_minute_limit, actor_burst_limit = effective_limits(account)
        cleanup_cutoff = now - timedelta(seconds=EVENT_RETENTION_SECONDS)
        db.query(ClickEvent).filter(ClickEvent.created_at < cleanup_cutoff).delete(synchronize_session=False)
        db.query(AccountClickEvent).filter(AccountClickEvent.created_at < cleanup_cutoff).delete(synchronize_session=False)
        db.query(UsedRequest).filter(UsedRequest.created_at < cleanup_cutoff).delete(synchronize_session=False)
        target = db.get(School, payload.school_id)
        if not target or not target.is_active:
            raise HTTPException(status_code=404, detail="Учебное заведение не найдено")
        if blocked(db, identity):
            log_abuse(db, "blocked_identity", identity, prefix, "Click from blocked identity")
            db.commit()
            raise HTTPException(status_code=403, detail="Доступ ограничен")
        if TURNSTILE_ENABLED and not captcha_is_verified(db, identity, now):
            log_abuse(db, "captcha_required", identity, prefix, "Click without verified Turnstile session")
            db.commit()
            raise HTTPException(status_code=403, detail="Пройдите проверку CAPTCHA")
        if suspicious_ua:
            log_abuse(db, "suspicious_user_agent", identity, prefix, request.headers.get("user-agent", "")[:300])
            db.commit()
            raise HTTPException(status_code=403, detail="Запрос заблокирован")

        usage = db.execute(select(VoterUsage).where(VoterUsage.identity_hash == identity).with_for_update()).scalar_one_or_none()
        if usage is None:
            usage = VoterUsage(identity_hash=identity, day=today_key(), clicks=0)
            db.add(usage)
            db.flush()
        used = db.get(UsedRequest, payload.request_id)
        if used is not None:
            minute_used = recent_clicks_for_identity(db, identity, now, 60)
            return {"ok": True, "accepted": 0, "rejected": payload.clicks, "duplicate": True, "remaining": max(0, minute_limit - minute_used), "limit_per_minute": minute_limit, "multiplier": VERIFIED_MULTIPLIER if account and account.is_subscriber else 1}

        minute_used = recent_clicks_for_identity(db, identity, now, 60)
        account_minute_used = recent_clicks_for_account(db, account.id, now, 60) if account else 0
        actor_minute_used = recent_clicks_for_actor(db, prefix, ua_hash, now, 60)
        burst = recent_clicks_for_identity(db, identity, now, 5)
        actor_burst = recent_clicks_for_actor(db, prefix, ua_hash, now, 5)
        active_event = db.query(GlobalGameEvent).filter(GlobalGameEvent.expires_at > now).order_by(GlobalGameEvent.id.desc()).first()
        normal_multiplier = VERIFIED_MULTIPLIER if account and account.is_subscriber else 1
        effect_per_tap = int(active_event.delta) if active_event else normal_multiplier
        rate_unit = max(1, abs(effect_per_tap))
        req_count = db.query(func.count(UsedRequest.request_id)).filter(
            UsedRequest.ip_prefix == prefix,
            UsedRequest.created_at >= now - timedelta(seconds=60),
        ).scalar() or 0
        if req_count >= IP_REQUEST_LIMIT_PER_MINUTE:
            log_abuse(db, "request_rate_limit", identity, prefix, f"requests={req_count}")
            db.commit()
            raise HTTPException(status_code=429, detail="Слишком много запросов")

        ip_usage = db.execute(select(IpDailyUsage).where(IpDailyUsage.ip_prefix == prefix, IpDailyUsage.day == today_key()).with_for_update()).scalar_one_or_none()
        if ip_usage is None:
            ip_usage = IpDailyUsage(ip_prefix=prefix, day=today_key(), clicks=0, updated_at=now)
            db.add(ip_usage)
            db.flush()
        if ip_usage.clicks >= IP_DAILY_CLICK_LIMIT:
            log_abuse(db, "ip_daily_click_limit", identity, prefix, f"ip_limit={IP_DAILY_CLICK_LIMIT};used={ip_usage.clicks}")
            db.commit()
            raise HTTPException(status_code=429, detail="Слишком много активности с одной сети")

        capacity = min(
            minute_limit - minute_used,
            (minute_limit - account_minute_used) if account else minute_limit,
            actor_minute_limit - actor_minute_used,
            burst_limit - burst,
            actor_burst_limit - actor_burst,
            IP_DAILY_CLICK_LIMIT - ip_usage.clicks,
        )
        accepted = max(0, min(payload.clicks, capacity) )
        rejected = payload.clicks - accepted
        awarded = accepted * effect_per_tap
        consumed_units = accepted * rate_unit
        consumed_taps = accepted
        if accepted:
            if awarded >= 0:
                target.real_clicks += awarded
            else:
                target.real_clicks = max(0, target.real_clicks + awarded)
            usage.clicks += consumed_taps
            usage.last_click_at = now
            ip_usage.clicks += consumed_taps
            ip_usage.updated_at = now
            # ClickEvent stores positive consumed units so rolling anti-abuse limits
            # remain correct even during a negative global event.
            db.add(ClickEvent(school_id=target.id, identity_hash=identity, clicks=consumed_units, taps=consumed_taps, created_at=now))
            if account:
                # Profile activity is raw user taps, not multiplied score.
                db.add(AccountClickEvent(account_id=account.id, clicks=accepted, created_at=now))
                account_school = db.execute(
                    select(AccountSchoolClick).where(
                        AccountSchoolClick.account_id == account.id,
                        AccountSchoolClick.school_id == target.id,
                    ).with_for_update()
                ).scalar_one_or_none()
                if account_school is None:
                    db.add(AccountSchoolClick(account_id=account.id, school_id=target.id, clicks=accepted, updated_at=now))
                else:
                    account_school.clicks += accepted
                    account_school.updated_at = now
        db.add(UsedRequest(request_id=payload.request_id, identity_hash=identity, ip_prefix=prefix, created_at=now))
        if rejected:
            log_abuse(db, "click_cap", identity, prefix, f"requested={payload.clicks};accepted={accepted};limit={minute_limit}")
        db.commit()
        remaining_identity = minute_limit - minute_used - consumed_taps
        remaining_account = minute_limit - account_minute_used - consumed_taps if account else minute_limit
        remaining = max(0, min(remaining_identity, remaining_account))
        return {
            "ok": True,
            "accepted": accepted,
            "rejected": rejected,
            "awarded": awarded,
            "remaining": remaining,
            "limit_per_minute": minute_limit,
            "multiplier": normal_multiplier,
            "event_delta": effect_per_tap if active_event else None,
        }


# ---------- Accounts ----------

@app.get("/api/account/me")
def account_me(request: Request):
    with SessionLocal() as db:
        account = user_session_account(db, request.cookies.get(USER_COOKIE))
        if not account:
            return {"authenticated": False}
        total_clicks = db.query(func.coalesce(func.sum(AccountSchoolClick.clicks), 0)).filter(AccountSchoolClick.account_id == account.id).scalar() or 0
        fav_row = db.query(AccountSchoolClick, School).join(School, School.id == AccountSchoolClick.school_id).filter(
            AccountSchoolClick.account_id == account.id, School.is_active == 1
        ).order_by(AccountSchoolClick.clicks.desc(), School.name.asc()).first()
        favorite = None
        if fav_row:
            linked, school = fav_row
            favorite = {"id": school.id, "name": school.name, "city": school.city, "clicks": int(linked.clicks)}
        return {
            "authenticated": True,
            "telegram_username": account.telegram_username,
            "verified_subscriber": bool(account.is_subscriber),
            "multiplier": VERIFIED_MULTIPLIER if account.is_subscriber else 1,
            "total_clicks": int(total_clicks),
            "favorite_school": favorite,
        }


@app.post("/api/account/verification/start")
def verification_start(payload: VerificationStartPayload, request: Request):
    require_same_origin(request)
    username = normalize_username(payload.telegram_username)
    if not username:
        raise HTTPException(status_code=400, detail="Укажите Telegram username")
    with SessionLocal() as db:
        if db.query(Account).filter(func.lower(Account.telegram_username) == username).first():
            raise HTTPException(status_code=409, detail="Этот username уже зарегистрирован. Используйте вход.")
        now = utcnow()
        db.query(TelegramVerificationChallenge).filter(
            TelegramVerificationChallenge.site_username == username,
            TelegramVerificationChallenge.used_at.is_(None),
        ).delete(synchronize_session=False)
        code = telegram_bot.new_code()
        challenge = TelegramVerificationChallenge(
            code_hash=telegram_bot.hash_code(code),
            site_username=username,
            created_at=now,
            expires_at=now + timedelta(minutes=BOT_CODE_MINUTES),
        )
        db.add(challenge)
        db.commit()
        db_url = bot_url()
    if not db_url:
        raise HTTPException(status_code=503, detail="Ссылка на Telegram-бота не настроена. Укажите TELEGRAM_BOT_USERNAME или TELEGRAM_BOT_URL.")
    deep_link = f"{db_url}?start={code}"
    return {"ok": True, "code": code, "bot_url": deep_link, "expires_at": iso_utc(challenge.expires_at), "username": username}


@app.get("/api/account/verification/status")
def verification_status(code: str):
    code = code.upper().strip()
    with SessionLocal() as db:
        row = db.get(TelegramVerificationChallenge, telegram_bot.hash_code(code))
        if not row or row.used_at or row.expires_at <= utcnow():
            return {"approved": False, "expired": True}
        return {
            "approved": bool(row.approved_at),
            "telegram_username": row.telegram_username or "",
            "site_username": row.site_username,
            "expires_at": iso_utc(row.expires_at),
        }


@app.post("/api/account/register")
def account_register(payload: AccountRegisterPayload, request: Request, response: Response):
    require_same_origin(request)
    username = normalize_username(payload.telegram_username)
    code = payload.code.upper().strip()
    with SessionLocal() as db:
        verification = db.get(TelegramVerificationChallenge, telegram_bot.hash_code(code))
        now = utcnow()
        if not verification or verification.used_at or verification.expires_at <= now:
            raise HTTPException(status_code=400, detail="Код недействителен или истёк. Сгенерируйте новый код.")
        if verification.site_username != username:
            raise HTTPException(status_code=400, detail="Username не совпадает с тем, для которого создан код")
        if not verification.approved_at or not verification.tg_user_id:
            raise HTTPException(status_code=400, detail="Сначала отправьте код боту и дождитесь подтверждения")
        verified_username = normalize_username(verification.telegram_username or "")
        if verified_username and verified_username != username:
            raise HTTPException(status_code=400, detail="Telegram username в боте не совпадает с username на сайте")
        if db.query(Account).filter(Account.tg_user_id == verification.tg_user_id).first():
            raise HTTPException(status_code=409, detail="Для этого Telegram уже есть аккаунт. Используйте вход.")
        salt, digest = password_hash(payload.password)
        # Подписка на канал НЕ обязательна для регистрации. Она влияет только на множитель кликов.
        account = Account(
            tg_user_id=verification.tg_user_id, telegram_username=username, password_salt=salt, password_hash=digest,
            created_at=now, verified_at=now, is_subscriber=0, last_subscription_check=None,
        )
        verification.used_at = now
        db.add(account)
        db.flush()
        token = secrets.token_urlsafe(48)
        db.add(UserSession(token_hash=hash_token(token), account_id=account.id, created_at=now, expires_at=now + timedelta(days=ACCOUNT_SESSION_DAYS)))
        db.commit()
    response.set_cookie(USER_COOKIE, token, max_age=ACCOUNT_SESSION_DAYS * 86400, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")
    return {"ok": True, "telegram_username": username, "verified_subscriber": False, "multiplier": 1}


@app.post("/api/account/login")
def account_login(payload: AccountLoginPayload, request: Request, response: Response):
    require_same_origin(request)
    username = normalize_username(payload.telegram_username)
    now = utcnow()
    with SessionLocal() as db:
        account = db.query(Account).filter(func.lower(Account.telegram_username) == username).first()
        if not account or not password_ok(payload.password, account.password_salt, account.password_hash):
            raise HTTPException(status_code=401, detail="Неверный username или пароль")
        if TELEGRAM_BOT_TOKEN and (not account.last_subscription_check or account.last_subscription_check < now - timedelta(minutes=SUBSCRIPTION_REFRESH_MINUTES)):
            try:
                import aiohttp
                import asyncio
                async def verify_member():
                    async with aiohttp.ClientSession(**telegram_bot.telegram_session_kwargs()) as http:
                        return await telegram_bot.check_subscription(http, int(account.tg_user_id))
                account.is_subscriber = 1 if asyncio.run(verify_member()) else 0
                account.last_subscription_check = now
            except Exception:
                pass
        token = secrets.token_urlsafe(48)
        db.add(UserSession(token_hash=hash_token(token), account_id=account.id, created_at=now, expires_at=now + timedelta(days=ACCOUNT_SESSION_DAYS)))
        db.commit()
        multiplier = VERIFIED_MULTIPLIER if account.is_subscriber else 1
    response.set_cookie(USER_COOKIE, token, max_age=ACCOUNT_SESSION_DAYS * 86400, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")
    return {"ok": True, "verified_subscriber": bool(multiplier == VERIFIED_MULTIPLIER), "multiplier": multiplier}


@app.post("/api/account/logout")
def account_logout(request: Request, response: Response):
    require_same_origin(request)
    token = request.cookies.get(USER_COOKIE)
    if token:
        with SessionLocal() as db:
            db.query(UserSession).filter(UserSession.token_hash == hash_token(token)).delete(synchronize_session=False)
            db.commit()
    response.delete_cookie(USER_COOKIE, path="/")
    return {"ok": True}


# ---------- Admin ----------

def require_admin(token: str | None):
    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход администратора")
    with SessionLocal() as db:
        row = db.get(AdminSession, hash_token(token))
        if not row or row.expires_at <= utcnow():
            raise HTTPException(status_code=401, detail="Сессия администратора истекла")


@app.get("/api/admin/me")
def admin_me(bitva_admin: str | None = Cookie(default=None)):
    if not bitva_admin:
        return {"authenticated": False}
    try:
        require_admin(bitva_admin)
    except HTTPException:
        return {"authenticated": False}
    return {"authenticated": True, "username": ADMIN_USERNAME}


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginPayload, request: Request, response: Response):
    require_same_origin(request)
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD не задан на сервере")
    prefix = ip_prefix(client_ip(request))
    since = utcnow() - timedelta(minutes=15)
    with SessionLocal() as db:
        failed = db.query(func.count(AbuseEvent.id)).filter(AbuseEvent.event_type == "admin_login_failed", AbuseEvent.ip_prefix == prefix, AbuseEvent.created_at >= since).scalar() or 0
        if failed >= 8:
            raise HTTPException(status_code=429, detail="Слишком много попыток входа. Попробуйте позже")
        if TURNSTILE_ENABLED and not verify_turnstile(payload.captcha_token or "", client_ip(request)):
            log_abuse(db, "admin_invalid_captcha", None, prefix, "admin login captcha failed")
            db.commit()
            raise HTTPException(status_code=403, detail="Проверка CAPTCHA не пройдена")
        if not (hmac.compare_digest(payload.username, ADMIN_USERNAME) and hmac.compare_digest(payload.password, ADMIN_PASSWORD)):
            log_abuse(db, "admin_login_failed", None, prefix, "invalid credentials")
            db.commit()
            raise HTTPException(status_code=401, detail="Неверные данные")
        token = secrets.token_urlsafe(48)
        db.add(AdminSession(token_hash=hash_token(token), created_at=utcnow(), expires_at=utcnow() + timedelta(hours=ADMIN_SESSION_HOURS), ip_prefix=prefix))
        db.commit()
    response.set_cookie(ADMIN_COOKIE, token, max_age=ADMIN_SESSION_HOURS * 3600, httponly=True, secure=COOKIE_SECURE, samesite="strict", path="/")
    return {"ok": True}


@app.post("/api/admin/logout")
def admin_logout(response: Response, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request)
    if bitva_admin:
        with SessionLocal() as db:
            db.query(AdminSession).filter(AdminSession.token_hash == hash_token(bitva_admin)).delete(synchronize_session=False)
            db.commit()
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/admin/dashboard")
def admin_dashboard(bitva_admin: str | None = Cookie(default=None)):
    require_admin(bitva_admin)
    with SessionLocal() as db:
        schools_count = db.query(func.count(School.id)).filter(School.is_active == 1).scalar() or 0
        total_clicks = db.query(func.coalesce(func.sum(score_expr()), 0)).filter(School.is_active == 1).scalar() or 0
        abuse_count = db.query(func.count(AbuseEvent.id)).scalar() or 0
        blocked_count = db.query(func.count(BlockedIdentity.identity_hash)).scalar() or 0
        source_national = db.query(func.count(School.id)).filter(School.origin == "national", School.is_active == 1).scalar() or 0
        accounts = db.query(func.count(Account.id)).scalar() or 0
        notices = db.query(BroadcastNotice).filter(BroadcastNotice.expires_at > utcnow()).order_by(BroadcastNotice.id.desc()).limit(5).all()
        events = db.query(AbuseEvent).order_by(AbuseEvent.created_at.desc()).limit(50).all()
    return {
        "schools_count": int(schools_count), "total_clicks": int(total_clicks), "abuse_events": int(abuse_count),
        "blocked_identities": int(blocked_count), "national_schools": int(source_national), "accounts": int(accounts),
        "active_notices": [{"id": n.id, "text": n.text, "expires_at": iso_utc(n.expires_at)} for n in notices],
        "abuse": [{"id": e.id, "created_at": iso_utc(e.created_at), "event_type": e.event_type, "identity": e.identity_hash, "ip_prefix": e.ip_prefix, "details": e.details} for e in events],
    }


@app.post("/api/admin/block")
def admin_block(payload: BlockPayload, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request)
    require_admin(bitva_admin)
    with SessionLocal() as db:
        db.merge(BlockedIdentity(identity_hash=payload.identity_hash, reason=clean_text(payload.reason, 500), created_at=utcnow()))
        db.commit()
    return {"ok": True}


@app.post("/api/admin/unblock")
def admin_unblock(payload: BlockPayload, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request)
    require_admin(bitva_admin)
    with SessionLocal() as db:
        db.query(BlockedIdentity).filter(BlockedIdentity.identity_hash == payload.identity_hash).delete(synchronize_session=False)
        db.commit()
    return {"ok": True}


@app.post("/api/admin/notice")
def admin_notice(payload: NoticePayload, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request)
    require_admin(bitva_admin)
    text_value = clean_text(payload.text, MAX_NOTICE_CHARS)
    if not text_value:
        raise HTTPException(status_code=400, detail="Введите текст")
    now = utcnow()
    with SessionLocal() as db:
        # Only one visible global message at a time.
        db.query(BroadcastNotice).filter(BroadcastNotice.expires_at <= now).delete(synchronize_session=False)
        row = BroadcastNotice(text=text_value, created_at=now, expires_at=now + timedelta(seconds=10), author=ADMIN_USERNAME)
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"ok": True, "id": row.id, "expires_at": iso_utc(row.expires_at)}


@app.get("/api/admin/settings")
def admin_settings(bitva_admin: str | None = Cookie(default=None)):
    require_admin(bitva_admin)
    with SessionLocal() as db:
        values = {}
        for key in ("about_text", "author_words", "donation_url"):
            row = db.get(SiteSetting, key)
            values[key] = row.value if row else ""
    return values


@app.post("/api/admin/settings")
def admin_settings_save(payload: SiteSettingsPayload, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request)
    require_admin(bitva_admin)
    donation = payload.donation_url.strip()
    parsed = urlparse(donation)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Ссылка на донат должна начинаться с http:// или https://")
    with SessionLocal() as db:
        for key, value in {"about_text": payload.about_text.strip(), "author_words": payload.author_words.strip(), "donation_url": donation}.items():
            row = db.get(SiteSetting, key)
            if row is None:
                db.add(SiteSetting(key=key, value=value, updated_at=utcnow()))
            else:
                row.value = value
                row.updated_at = utcnow()
        db.commit()
    return {"ok": True}


@app.get("/api/event/active")
def active_event():
    now = utcnow()
    with SessionLocal() as db:
        event = db.query(GlobalGameEvent).filter(GlobalGameEvent.expires_at > now).order_by(GlobalGameEvent.id.desc()).first()
        if not event:
            return {"active": False}
        return {
            "active": True, "id": event.id, "delta": int(event.delta),
            "effect": "plus" if event.delta >= 0 else "minus",
            "school": "Все школы", "city": "",
            "music_url": f"/assets/{event.music_path}" if event.music_path else "",
            "created_at": iso_utc(event.created_at), "expires_at": iso_utc(event.expires_at),
        }


@app.post("/api/admin/event")
async def admin_event(
    request: Request,
    bitva_admin: str | None = Cookie(default=None),
    effect: str = Form("plus"),
    amount: int = Form(10),
    duration: int = Form(GAME_EVENT_SECONDS),
    music: UploadFile | None = File(default=None),
):
    require_same_origin(request)
    require_admin(bitva_admin)
    effect = effect.strip().lower()
    if effect not in {"plus", "minus"}:
        raise HTTPException(status_code=400, detail="Выберите + или −")
    amount = max(1, min(int(amount), 1000))
    duration = max(3, min(int(duration), 60))
    audio_rel = None
    if music:
        allowed = {"audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav"}
        suffix = allowed.get((music.content_type or "").lower())
        if not suffix:
            raise HTTPException(status_code=400, detail="Музыка: только MP3, OGG или WAV")
        raw = await music.read()
        if len(raw) > MAX_EVENT_AUDIO_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Музыка слишком большая. Максимум {MAX_EVENT_AUDIO_MB} МБ")
        file_name = f"event-{secrets.token_urlsafe(16)}{suffix}"
        (EVENT_UPLOAD_DIR / file_name).write_bytes(raw)
        audio_rel = f"uploads/events/{file_name}"
    delta = amount if effect == "plus" else -amount
    now = utcnow()
    with SessionLocal() as db:
        db.query(GlobalGameEvent).filter(GlobalGameEvent.expires_at > now).update({GlobalGameEvent.expires_at: now}, synchronize_session=False)
        event = GlobalGameEvent(school_id=None, delta=delta, music_path=audio_rel, created_at=now, expires_at=now + timedelta(seconds=duration))
        db.add(event); db.commit(); db.refresh(event)
        return {"ok": True, "id": event.id, "delta": int(delta), "school": "Все школы", "expires_at": iso_utc(event.expires_at)}


@app.get("/api/admin/countries")
def admin_countries(bitva_admin: str | None = Cookie(default=None)):
    require_admin(bitva_admin)
    with SessionLocal() as db:
        rows = db.query(SiteCountry).filter(SiteCountry.is_active == 1).order_by(SiteCountry.sort_order.asc(), SiteCountry.name.asc()).all()
        return {"countries": [{"name": r.name, "school_count": int(db.query(func.count(School.id)).filter(School.is_active == 1, School.country == r.name).scalar() or 0)} for r in rows]}


@app.post("/api/admin/countries")
def admin_add_country(payload: CountryPayload, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request)
    require_admin(bitva_admin)
    name = clean_text(payload.name, 80)
    with SessionLocal() as db:
        if db.get(SiteCountry, name):
            raise HTTPException(status_code=409, detail="Такая страна уже есть")
        db.add(SiteCountry(name=name, is_active=1, sort_order=100, created_at=utcnow()))
        db.commit()
    return {"ok": True, "country": name}


@app.get("/api/admin/schools")
def admin_schools(page: int = 1, per_page: int = 100, q: str = "", city: str = "", country: str = "", photo: str = "", bitva_admin: str | None = Cookie(default=None)):
    require_admin(bitva_admin)
    page = max(1, min(page, 10000))
    per_page = max(20, min(per_page, 200))
    q = clean_text(q, 120)
    city = clean_text(city, 160)
    country = clean_text(country, 80)
    photo = clean_text(photo, 20).lower()
    with SessionLocal() as db:
        query = db.query(School)
        if country:
            query = query.filter(School.country == country)
        if city:
            query = query.filter(School.city == city)
        if q:
            like = f"%{q}%"
            query = query.filter((School.name.ilike(like)) | (School.city.ilike(like)) | (School.region.ilike(like)))
        if photo == "yes":
            query = query.filter(School.image_source == "upload")
        elif photo == "no":
            query = query.filter(School.image_source != "upload")
        total = query.count()
        rows = query.order_by(School.city.asc(), School.name.asc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "page": page,
        "per_page": per_page,
        "total": int(total),
        "items": [{
            "id": r.id, "name": r.name, "country": r.country, "region": r.region or "Россия", "city": r.city,
            "category": r.category, "category_label": r.category_label, "clicks": int(r.real_clicks + r.artificial_clicks),
            "image_source": r.image_source, "origin": r.origin, "active": bool(r.is_active),
        } for r in rows],
    }


@app.post("/api/admin/schools")
async def admin_add_school(
    request: Request,
    bitva_admin: str | None = Cookie(default=None),
    name: str = Form(...),
    country: str = Form("Россия"),
    region: str = Form(""),
    city: str = Form(...),
    category: str = Form(...),
    photo: UploadFile | None = File(default=None),
):
    require_same_origin(request)
    require_admin(bitva_admin)
    name = clean_text(name, 500)
    country = clean_text(country, 80) or "Россия"
    region = clean_text(region, 150) or ""
    city = clean_text(city, 160)
    category = clean_text(category, 50)
    if not name or not city or category not in CATEGORY_LABELS:
        raise HTTPException(status_code=400, detail="Заполните название, город и категорию")
    key = school_key(city, category, name)
    school_identifier = school_id(city, category, name)
    photo_source = "placeholder"
    if photo:
        if photo.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=400, detail="Фото: только JPG, PNG или WebP")
        raw = await photo.read()
        if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Фото слишком большое. Максимум {MAX_UPLOAD_MB} МБ")
        try:
            from PIL import Image, ImageOps
            import io
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)).convert("RGB"))
            img.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
            target_dir = UPLOAD_DIR / school_identifier
            target_dir.mkdir(parents=True, exist_ok=True)
            img.save(target_dir / "photo.webp", "WEBP", quality=82, method=6)
            photo_source = "upload"
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Не удалось обработать изображение: {exc.__class__.__name__}")
    with SessionLocal() as db:
        if db.get(SiteCountry, country) is None:
            db.add(SiteCountry(name=country, is_active=1, sort_order=100, created_at=utcnow()))
            db.flush()
        if db.scalar(select(School).where(School.normalized_key == key)):
            raise HTTPException(status_code=409, detail="Такое учебное заведение уже есть в этом городе и категории")
        db.add(School(
            id=school_identifier,
            country=country,
            region=region or None,
            city=city,
            category=category,
            category_label=CATEGORY_LABELS[category],
            name=name,
            folder=f"manual/{school_identifier}",
            normalized_key=key,
            image_source=photo_source,
            origin="manual",
            is_active=1,
            real_clicks=0,
            artificial_clicks=0,
            created_at=utcnow(),
        ))
        db.commit()
    return {"ok": True, "school": {"id": school_identifier, "name": name, "city": city}}


@app.post("/api/admin/schools/{school_id}/photo")
async def admin_school_photo(
    school_id: str,
    request: Request,
    bitva_admin: str | None = Cookie(default=None),
    photo: UploadFile = File(...),
):
    require_same_origin(request)
    require_admin(bitva_admin)
    if photo.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="Фото: только JPG, PNG или WebP")
    raw = await photo.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Фото слишком большое. Максимум {MAX_UPLOAD_MB} МБ")
    try:
        from PIL import Image, ImageOps
        import io
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)).convert("RGB"))
        img.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
        target_dir = UPLOAD_DIR / school_id
        target_dir.mkdir(parents=True, exist_ok=True)
        img.save(target_dir / "photo.webp", "WEBP", quality=82, method=6)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось обработать изображение: {exc.__class__.__name__}")
    with SessionLocal() as db:
        school = db.get(School, school_id)
        if not school or not school.is_active:
            raise HTTPException(status_code=404, detail="Учебное заведение не найдено")
        school.image_source = "upload"
        db.commit()
    return {"ok": True, "school_id": school_id, "image_source": "upload"}


@app.post("/api/photo-submissions")
async def submit_school_photo(
    request: Request, response: Response,
    country: str = Form(...), city: str = Form(...), school_id: str = Form(...),
    consent: str = Form(...), photo: UploadFile = File(...),
):
    require_same_origin(request)
    if consent.lower() not in {"1", "true", "on", "yes"}:
        raise HTTPException(status_code=400, detail="Нужно подтвердить согласие с правилами загрузки")
    if photo.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="Фото: только JPG, PNG или WebP")
    raw = await photo.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Фото слишком большое. Максимум {MAX_UPLOAD_MB} МБ")
    with SessionLocal() as db:
        school = db.get(School, clean_text(school_id, 100))
        if not school or not school.is_active or school.country != clean_text(country, 80) or school.city != clean_text(city, 160):
            raise HTTPException(status_code=400, detail="Выбранная школа не соответствует городу или стране")
        try:
            from PIL import Image, ImageOps
            import io
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)).convert("RGB"))
            img.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
            sub_id = secrets.token_urlsafe(12)
            rel = f"uploads/submissions/{sub_id}.webp"
            target = STATIC_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target, "WEBP", quality=82, method=6)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Не удалось обработать изображение: {exc.__class__.__name__}")
        identity, _, _ = ensure_identity(request, response)
        account = user_session_account(db, request.cookies.get(USER_COOKIE))
        row = PhotoSubmission(school_id=school.id, country=school.country, city=school.city, file_path=rel, original_name=clean_text(photo.filename or "photo",255), consent=1, submitter_identity=identity, submitter_account_id=account.id if account else None)
        db.add(row); db.commit()
    return {"ok": True, "message": "Фото отправлено на модерацию. После проверки администратором оно появится в рейтинге."}


@app.get("/api/admin/photo-submissions")
def admin_photo_submissions(status: str = "pending", page: int = 1, per_page: int = 50, bitva_admin: str | None = Cookie(default=None)):
    require_admin(bitva_admin)
    status = clean_text(status, 20) or "pending"
    with SessionLocal() as db:
        q = db.query(PhotoSubmission).filter(PhotoSubmission.status == status)
        total = q.count(); rows = q.order_by(PhotoSubmission.created_at.desc()).offset((max(1,page)-1)*per_page).limit(min(100,max(10,per_page))).all()
        items=[]
        for r in rows:
            school=db.get(School,r.school_id)
            items.append({"id":r.id,"school_id":r.school_id,"school":school.name if school else r.school_id,"city":r.city,"country":r.country,"file_url":"/assets/"+r.file_path,"original_name":r.original_name,"created_at":iso_utc(r.created_at),"status":r.status})
        return {"total":int(total),"items":items}


@app.post("/api/admin/photo-submissions/{submission_id}/approve")
def approve_photo_submission(submission_id: int, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request); require_admin(bitva_admin)
    with SessionLocal() as db:
        sub=db.get(PhotoSubmission,submission_id); school=db.get(School,sub.school_id) if sub else None
        if not sub or not school or sub.status != "pending": raise HTTPException(status_code=404,detail="Заявка не найдена")
        source=STATIC_DIR/sub.file_path
        if not source.exists(): raise HTTPException(status_code=404,detail="Файл заявки не найден")
        target_dir=UPLOAD_DIR/school.id; target_dir.mkdir(parents=True,exist_ok=True); (target_dir/"photo.webp").write_bytes(source.read_bytes())
        school.image_source="upload"; sub.status="approved"; sub.reviewed_at=utcnow(); db.commit()
        return {"ok":True}


@app.post("/api/admin/photo-submissions/{submission_id}/reject")
def reject_photo_submission(submission_id: int, request: Request, bitva_admin: str | None = Cookie(default=None), reason: str = Form("")):
    require_same_origin(request); require_admin(bitva_admin)
    with SessionLocal() as db:
        sub=db.get(PhotoSubmission,submission_id)
        if not sub or sub.status != "pending": raise HTTPException(status_code=404,detail="Заявка не найдена")
        sub.status="rejected"; sub.rejection_reason=clean_text(reason,500); sub.reviewed_at=utcnow(); db.commit(); return {"ok":True}


@app.delete("/api/admin/schools/{school_id}/photo")
def admin_delete_school_photo(school_id: str, request: Request, bitva_admin: str | None = Cookie(default=None)):
    require_same_origin(request); require_admin(bitva_admin)
    with SessionLocal() as db:
        school=db.get(School,school_id)
        if not school: raise HTTPException(status_code=404,detail="Учебное заведение не найдено")
        target=UPLOAD_DIR/school_id/"photo.webp"
        try: target.unlink(missing_ok=True)
        except Exception: pass
        school.image_source="placeholder"; db.commit(); return {"ok":True}


@app.get("/privacy")
def privacy_page():
    return FileResponse(STATIC_DIR / "privacy.html")


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "bitva-shkol", "time": utcnow().isoformat()}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
