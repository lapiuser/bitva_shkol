# Wasmer deployment

This build is prepared for Wasmer's Python/Anybuild preset.

1. Upload the ZIP contents as the project source.
2. Project preset: Python.
3. Do not add an Install Command manually.
4. Environment variables: configure the production values from `.env.production.example`.
5. Enable the Wasmer database and choose MySQL; the app reads DB_HOST/DB_NAME/DB_USERNAME/DB_PORT/DB_PASSWORD automatically.
6. Deploy.

The root `requirements.txt` is intentionally absent. Dependencies are declared in the root `Anybuild` file for Wasmer, while Docker/Timeweb uses `deploy/timeweb/requirements.txt`.


## Постоянное хранение данных

Для реального запуска обязательно включи **Enable Database** в Wasmer. После деплоя `/api/config` должен показывать `storage: "mysql"`. Если там `sqlite`, тестовые данные могут пропасть после пересоздания контейнера/перезапуска.

## Cloudflare Turnstile

В Cloudflare создай Turnstile widget для своего домена и выбери режим **Invisible**. В Wasmer добавь:

- `TURNSTILE_ENABLED=true`
- `TURNSTILE_SITE_KEY=<Site Key>`
- `TURNSTILE_SECRET_KEY=<Secret Key>`
- `TURNSTILE_MODE=invisible`

Проверка Turnstile выполняется на сервере. Сам Turnstile предназначен для проверки действий/запросов, а полноценную защиту от DDoS дает проксирование домена через Cloudflare.


## Wasmer managed database

Select MySQL in Wasmer's Enable Database section. Wasmer exposes DB_HOST, DB_NAME, DB_USERNAME, DB_PORT and DB_PASSWORD automatically; the app builds DATABASE_URL from them when DATABASE_URL is not set.


## Telegram on Wasmer

The bot uses the standard `certifi` CA bundle and `trust_env=true` for outbound Telegram HTTPS. Keep `TELEGRAM_SSL_VERIFY=true` normally. If Wasmer's outbound network still presents a private/self-signed certificate, set `TELEGRAM_CA_FILE` to the CA bundle provided by the platform or, only as a temporary diagnostic option, set `TELEGRAM_SSL_VERIFY=false`. Disabling TLS verification is not recommended for production because the Telegram Bot API traffic contains the bot token and verification data.

## Countries and cities

The first selection screen is now country-first. Russia is seeded by default. Admin can add another country; its cities become selectable automatically as schools are added under that country.

## Click protection

Authenticated users have a strict rolling 60-second account limit in the database: 800 clicks/minute, or 2400 for a verified Telegram subscriber. Device/IP/user-agent limits remain as an additional protection for guests. No web application can literally guarantee that an anonymous attacker will never create another identity, so production should put the domain behind Cloudflare as well.
