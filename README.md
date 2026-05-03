# Escrow Garant Bot

Telegram escrow bot built with **aiogram 3 + SQLite (aiosqlite)**.

## Stack
- aiogram 3
- sqlite3 via aiosqlite
- pydantic-settings

## Quick start

1. Copy env file:

```bash
cp .env.example .env
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run bot (schema auto-initializes on startup):

```bash
python run.py
```

4. Optional scheduler (auto-cancel expired pending deals):

```bash
python scripts/run_scheduler.py
```


## CryptoBot deposits

Set `CRYPTOBOT_TOKEN` in `.env` to enable invoice-based deposits via CryptoBot API.

Two payment confirmation modes are supported:

1. **Manual check button** (`✅ I have paid`) in Telegram.
2. **Automatic webhook crediting** from CryptoBot (`invoice_paid` event).

### Webhook server settings

Bot starts webhook HTTP server on startup with:

- `CRYPTOBOT_WEBHOOK_HOST` (default `0.0.0.0`)
- `CRYPTOBOT_WEBHOOK_PORT` (default `8081`)
- `CRYPTOBOT_WEBHOOK_PATH` (default `/cryptobot/webhook`)

So local webhook URL is:

`http://<your_server_ip>:<CRYPTOBOT_WEBHOOK_PORT><CRYPTOBOT_WEBHOOK_PATH>`

Check listener locally:

```bash
ss -lntp | grep 8081
```

### Domain setup example (recommended)

1. Point A-record of your domain/subdomain (for example `pay.example.com`) to your server IP.
2. Put Nginx in front of bot webhook port and enable HTTPS (Let's Encrypt).
3. Proxy webhook route to bot:

```nginx
server {
    server_name pay.example.com;

    location /cryptobot/webhook {
        proxy_pass http://127.0.0.1:8081/cryptobot/webhook;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

4. Register webhook URL in CryptoBot API (replace token and URL):

```bash
curl -X POST "https://pay.crypt.bot/api/setWebhook" \
  -H "Crypto-Pay-API-Token: <CRYPTOBOT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://pay.example.com/cryptobot/webhook"}'
```

5. Keep manual `✅ I have paid` button enabled as fallback (already implemented).
