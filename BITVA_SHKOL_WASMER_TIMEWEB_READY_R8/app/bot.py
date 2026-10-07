from __future__ import annotations

import asyncio
import hashlib
import secrets
import ssl
from datetime import timedelta

import aiohttp
import certifi

from .config import (
    BOT_CODE_MINUTES,
    BOT_POLLING_ENABLED,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_URL,
    TELEGRAM_BOT_USERNAME,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_CHANNEL_USERNAME,
    SITE_PUBLIC_URL,
    TELEGRAM_CA_FILE, TELEGRAM_SSL_VERIFY,
)
from .db import SessionLocal, TelegramVerificationChallenge, TelegramVerificationCode, utcnow

BOT_TASK: asyncio.Task | None = None
STOP_EVENT: asyncio.Event | None = None
BOT_USERNAME_RUNTIME = TELEGRAM_BOT_USERNAME


def hash_code(code: str) -> str:
    return hashlib.sha256(code.upper().strip().encode("utf-8")).hexdigest()


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def channel_targets() -> list[str]:
    values = []
    if TELEGRAM_CHANNEL_USERNAME:
        values.append(TELEGRAM_CHANNEL_USERNAME)
    if TELEGRAM_CHANNEL_ID:
        values.append(TELEGRAM_CHANNEL_ID)
        raw = TELEGRAM_CHANNEL_ID.lstrip("-")
        if raw.isdigit() and not TELEGRAM_CHANNEL_ID.startswith("-100"):
            values.append(f"-100{raw}")
    return list(dict.fromkeys(values))


def is_subscribed_status(member: dict | None) -> bool:
    if not member:
        return False
    status = str(member.get("status", ""))
    if status in {"creator", "administrator", "member"}:
        return True
    if status == "restricted":
        return bool(member.get("is_member"))
    return False


def telegram_ssl_context():
    if not TELEGRAM_SSL_VERIFY:
        return False
    cafile = TELEGRAM_CA_FILE or certifi.where()
    try:
        return ssl.create_default_context(cafile=cafile)
    except Exception as exc:
        print(f"[bot] cannot load CA bundle {cafile!r}: {exc}", flush=True)
        return ssl.create_default_context()


def telegram_session_kwargs() -> dict:
    return {
        "timeout": aiohttp.ClientTimeout(total=35),
        "connector": aiohttp.TCPConnector(limit=8, ttl_dns_cache=300, ssl=telegram_ssl_context()),
        "trust_env": True,
    }


async def tg_call(session: aiohttp.ClientSession, method: str, payload: dict) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=35)) as resp:
        data = await resp.json(content_type=None)
        if not resp.ok or not data.get("ok"):
            raise RuntimeError(str(data.get("description") or f"Telegram HTTP {resp.status}"))
        return data


async def check_subscription(session: aiohttp.ClientSession, user_id: int) -> bool:
    last_error = None
    for chat_id in channel_targets():
        try:
            data = await tg_call(session, "getChatMember", {"chat_id": chat_id, "user_id": user_id})
            return is_subscribed_status(data.get("result"))
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return False


def create_verification_code(tg_user_id: int, username: str) -> str:
    code = new_code()
    now = utcnow()
    with SessionLocal() as db:
        db.query(TelegramVerificationCode).filter(
            TelegramVerificationCode.tg_user_id == str(tg_user_id),
            TelegramVerificationCode.used_at.is_(None),
        ).delete(synchronize_session=False)
        db.add(
            TelegramVerificationCode(
                code_hash=hash_code(code),
                tg_user_id=str(tg_user_id),
                telegram_username=username,
                created_at=now,
                expires_at=now + timedelta(minutes=BOT_CODE_MINUTES),
            )
        )
        db.commit()
    return code


async def send_message(session: aiohttp.ClientSession, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await tg_call(session, "sendMessage", payload)


async def answer_callback(session: aiohttp.ClientSession, callback_id: str, text: str = "") -> None:
    await tg_call(session, "answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": False})


def subscribe_markup() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Подписаться на канал", "url": "https://t.me/AntonLjungberg"}],
            [{"text": "Проверить подписку", "callback_data": "check_sub"}],
        ]
    }


def bot_base_url() -> str:
    configured = TELEGRAM_BOT_URL.strip()
    if configured:
        base = configured.split("?", 1)[0].rstrip("/")
        return base
    return f"https://t.me/{TELEGRAM_BOT_USERNAME.lstrip('@')}" if TELEGRAM_BOT_USERNAME else ""

def site_markup() -> dict | None:
    url = SITE_PUBLIC_URL
    if url:
        return {"inline_keyboard": [[{"text": "Открыть сайт", "url": url}]]}
    return None


async def approve_site_challenge(session: aiohttp.ClientSession, chat_id: int, user_id: int, username: str, code: str) -> bool:
    code = code.upper().strip()
    now = utcnow()
    with SessionLocal() as db:
        challenge = db.get(TelegramVerificationChallenge, hash_code(code))
        if not challenge or challenge.used_at or challenge.expires_at <= now:
            return False
        if challenge.approved_at:
            await send_message(session, chat_id, "Этот код уже подтверждён. Вернитесь на сайт и завершите регистрацию.")
            return True
    with SessionLocal() as db:
        challenge = db.get(TelegramVerificationChallenge, hash_code(code))
        if not challenge or challenge.used_at or challenge.expires_at <= utcnow():
            await send_message(session, chat_id, "Код истёк. Создайте новый код на сайте.")
            return True
        challenge.tg_user_id = str(user_id)
        challenge.telegram_username = username or ""
        challenge.approved_at = utcnow()
        db.commit()
    await send_message(session, chat_id, "Telegram подтверждён. Вернитесь на сайт — регистрация уже разблокируется автоматически.", site_markup())
    return True


async def issue_code(session: aiohttp.ClientSession, chat_id: int, user_id: int, username: str) -> None:
    await send_message(
        session,
        chat_id,
        "Для регистрации откройте сайт, введите Telegram username и пароль, нажмите «Сгенерировать код», затем отправьте код этому боту. Подписка на канал для регистрации не обязательна.",
        site_markup(),
    )


async def process_update(session: aiohttp.ClientSession, update: dict) -> None:
    global BOT_USERNAME_RUNTIME
    if update.get("callback_query"):
        cq = update["callback_query"]
        user = cq.get("from") or {}
        chat = cq.get("message", {}).get("chat", {})
        if cq.get("data") == "check_sub":
            await answer_callback(session, str(cq.get("id")), "Проверяю…")
            subscribed = False
            try:
                subscribed = await check_subscription(session, int(user.get("id")))
                reply = "Подписка подтверждена. На сайте обновится множитель ×3." if subscribed else "Подписка не найдена. Подпишитесь на канал и нажмите «Проверить подписку» ещё раз."
            except Exception:
                reply = "Не удалось проверить подписку. Убедитесь, что бот является администратором канала."
            await send_message(session, int(chat.get("id", user.get("id"))), reply, subscribe_markup() if not subscribed else site_markup())
        return

    message = update.get("message") or {}
    text = str(message.get("text") or "").strip()
    if not text:
        return
    user = message.get("from") or {}
    chat = message.get("chat") or {}
    user_id = int(user.get("id"))
    chat_id = int(chat.get("id"))
    username = str(user.get("username") or "")
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()

    if command == "/start":
        arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        if arg and len(arg) >= 8 and await approve_site_challenge(session, chat_id, user_id, username, arg):
            return
        await issue_code(session, chat_id, user_id, username)
    elif command in {"/code", "/verify"}:
        await issue_code(session, chat_id, user_id, username)
    elif len(text.replace(" ", "")) == 8 and await approve_site_challenge(session, chat_id, user_id, username, text.replace(" ", "")):
        return
    elif command == "/status":
        try:
            subscribed = await check_subscription(session, user_id)
            reply = "Подписка подтверждена." if subscribed else "Подписка не найдена."
        except Exception:
            reply = "Не удалось проверить подписку. Проверьте, что бот остаётся администратором канала."
        await send_message(session, chat_id, reply, subscribe_markup() if "не найдена" in reply else None)
    elif command == "/help":
        await send_message(session, chat_id, "Команды: /start — проверка подписки и код, /status — статус подписки, /help — помощь.")


async def poll_loop() -> None:
    global BOT_USERNAME_RUNTIME
    if not TELEGRAM_BOT_TOKEN or not BOT_POLLING_ENABLED:
        print("[bot] disabled: TELEGRAM_BOT_TOKEN missing or BOT_POLLING_ENABLED=false", flush=True)
        return
    timeout = 25
    offset = None
    async with aiohttp.ClientSession(**telegram_session_kwargs()) as session:
        try:
            await tg_call(session, "deleteWebhook", {"drop_pending_updates": True})
            me = await tg_call(session, "getMe", {})
            BOT_USERNAME_RUNTIME = str(me.get("result", {}).get("username") or BOT_USERNAME_RUNTIME)
            if BOT_USERNAME_RUNTIME:
                print(f"[bot] @{BOT_USERNAME_RUNTIME} online", flush=True)
        except Exception as exc:
            print(f"[bot] startup check failed: {exc}", flush=True)
        while STOP_EVENT is None or not STOP_EVENT.is_set():
            try:
                payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    payload["offset"] = offset
                data = await tg_call(session, "getUpdates", payload)
                for update in data.get("result", []):
                    offset = int(update["update_id"]) + 1
                    try:
                        await process_update(session, update)
                    except Exception as exc:
                        print(f"[bot] update error: {exc}", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[bot] polling error: {exc}", flush=True)
                await asyncio.sleep(3)


async def start_bot() -> None:
    global BOT_TASK, STOP_EVENT, BOT_USERNAME_RUNTIME
    if BOT_TASK and not BOT_TASK.done():
        return
    if TELEGRAM_BOT_TOKEN and BOT_POLLING_ENABLED:
        try:
            async with aiohttp.ClientSession(**telegram_session_kwargs()) as session:
                me = await tg_call(session, "getMe", {})
                BOT_USERNAME_RUNTIME = str(me.get("result", {}).get("username") or BOT_USERNAME_RUNTIME)
        except Exception as exc:
            print(f"[bot] getMe failed before start: {exc}", flush=True)
    STOP_EVENT = asyncio.Event()
    BOT_TASK = asyncio.create_task(poll_loop(), name="bitva-telegram-bot")


async def stop_bot() -> None:
    global BOT_TASK, STOP_EVENT
    if STOP_EVENT:
        STOP_EVENT.set()
    if BOT_TASK:
        BOT_TASK.cancel()
        try:
            await BOT_TASK
        except asyncio.CancelledError:
            pass
    BOT_TASK = None
    STOP_EVENT = None
