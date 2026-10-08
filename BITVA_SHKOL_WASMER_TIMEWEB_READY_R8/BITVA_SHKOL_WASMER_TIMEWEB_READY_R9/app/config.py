from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "schools"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database: prefer an explicit DATABASE_URL. Wasmer's managed database
# exposes DB_HOST/DB_NAME/DB_USERNAME/DB_PORT/DB_PASSWORD, so build a
# SQLAlchemy URL automatically when DATABASE_URL is not provided.
_db_url = os.getenv("DATABASE_URL", "").strip()
if _db_url:
    DATABASE_URL = _db_url
elif os.getenv("DB_HOST") and os.getenv("DB_NAME") and os.getenv("DB_USERNAME"):
    DATABASE_URL = (
        "mysql+pymysql://"
        + os.getenv("DB_USERNAME", "")
        + ":" + os.getenv("DB_PASSWORD", "")
        + "@" + os.getenv("DB_HOST", "")
        + ":" + os.getenv("DB_PORT", "3306")
        + "/" + os.getenv("DB_NAME", "")
    )
else:
    DATABASE_URL = f"sqlite:///{(DATA_DIR / 'leaderboard.db').as_posix()}"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

APP_HOST = os.getenv("HOST", "127.0.0.1")
APP_PORT = int(os.getenv("PORT", "8000"))
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Fair-use protection. Base users get 800 clicks/minute. Verified subscribers get x3.
CLICK_LIMIT_PER_MINUTE = int(os.getenv("CLICK_LIMIT_PER_MINUTE", "800"))
CLICK_MAX_PER_REQUEST = int(os.getenv("CLICK_MAX_PER_REQUEST", str(CLICK_LIMIT_PER_MINUTE * 3)))
CLICK_BURST_LIMIT_5S = int(os.getenv("CLICK_BURST_LIMIT_5S", str(CLICK_LIMIT_PER_MINUTE)))
ACTOR_CLICK_LIMIT_PER_MINUTE = int(os.getenv("ACTOR_CLICK_LIMIT_PER_MINUTE", str(CLICK_LIMIT_PER_MINUTE)))
ACTOR_BURST_LIMIT_5S = int(os.getenv("ACTOR_BURST_LIMIT_5S", str(CLICK_LIMIT_PER_MINUTE)))
VERIFIED_MULTIPLIER = int(os.getenv("VERIFIED_MULTIPLIER", "3"))
IP_REQUEST_LIMIT_PER_MINUTE = int(os.getenv("IP_REQUEST_LIMIT_PER_MINUTE", "120"))
IP_DAILY_CLICK_LIMIT = int(os.getenv("IP_DAILY_CLICK_LIMIT", "24000"))
ACTIVE_USER_SECONDS = int(os.getenv("ACTIVE_USER_SECONDS", "60"))
EVENT_RETENTION_SECONDS = int(os.getenv("EVENT_RETENTION_SECONDS", "900"))

# CAPTCHA
TURNSTILE_ENABLED = os.getenv("TURNSTILE_ENABLED", "false").lower() == "true"
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_MODE = os.getenv("TURNSTILE_MODE", "invisible").strip().lower()
CAPTCHA_SESSION_MINUTES = int(os.getenv("CAPTCHA_SESSION_MINUTES", "20"))

# Administration
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "nfu93amonyunker")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SESSION_HOURS = int(os.getenv("ADMIN_SESSION_HOURS", "12"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
MAX_NOTICE_CHARS = int(os.getenv("MAX_NOTICE_CHARS", "240"))
MAX_EVENT_AUDIO_MB = int(os.getenv("MAX_EVENT_AUDIO_MB", "12"))
GAME_EVENT_SECONDS = int(os.getenv("GAME_EVENT_SECONDS", "10"))

# Telegram integration. Never commit the bot token to GitHub.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "4380132206").strip()
TELEGRAM_CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME", "@AntonLjungberg").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "").strip()
SITE_PUBLIC_URL = os.getenv("SITE_PUBLIC_URL", "").strip().rstrip("/")
BOT_POLLING_ENABLED = os.getenv("BOT_POLLING_ENABLED", "true").lower() == "true"
BOT_CODE_MINUTES = int(os.getenv("BOT_CODE_MINUTES", "10"))
ACCOUNT_SESSION_DAYS = int(os.getenv("ACCOUNT_SESSION_DAYS", "30"))
SUBSCRIPTION_REFRESH_MINUTES = int(os.getenv("SUBSCRIPTION_REFRESH_MINUTES", "15"))
TELEGRAM_SSL_VERIFY = os.getenv("TELEGRAM_SSL_VERIFY", "true").lower() == "true"
TELEGRAM_CA_FILE = os.getenv("TELEGRAM_CA_FILE", "").strip()
TELEGRAM_INSECURE_SSL_FALLBACK = os.getenv("TELEGRAM_INSECURE_SSL_FALLBACK", "false").lower() == "true"

# UI/content
DONATION_URL = os.getenv("DONATION_URL", "https://www.donationalerts.com/")
AUTHOR_WORDS = os.getenv(
    "AUTHOR_WORDS",
    "БИТВА ШКОЛ — независимый рейтинг, где учебные заведения соревнуются за реальную поддержку людей. "
    "Результат формируется сервером, а защита и ограничения нужны для честной игры.",
)
ABOUT_TEXT = os.getenv(
    "ABOUT_TEXT",
    "БИТВА ШКОЛ — интерактивный рейтинг учебных заведений России. Выберите город, категорию и учебное заведение. "
    "Новые школы и фотографии добавляются вручную через панель администратора.",
)
STATS_REFRESH_SECONDS = int(os.getenv("STATS_REFRESH_SECONDS", "10"))
RATING_REFRESH_SECONDS = int(os.getenv("RATING_REFRESH_SECONDS", "10"))
