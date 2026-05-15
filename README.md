# Placement WhatsApp Notifier

Monitors **only** unread placement emails from `cvr.placement@gmail.com` and `alerts@haveloc.com`, parses full content (HTML + plain text), and forwards alerts to WhatsApp using **WhatsApp Web + Selenium** (no Twilio).

## Features

- FastAPI backend with health check and manual scan endpoint
- Gmail API with OAuth2 (strict sender + unread query only)
- BeautifulSoup HTML-to-text conversion
- WhatsApp Web automation via Chrome (persistent login session)
- Duplicate prevention via stored Gmail message IDs
- Background polling every 30 seconds

## Project structure

```
placement_notifier/
├── app/
│   ├── main.py
│   ├── gmail_service.py
│   ├── whatsapp_service.py
│   ├── parser.py
│   ├── config.py
│   └── state.py
├── requirements.txt
├── .env.example
└── README.md
```

## Prerequisites

1. **Python 3.10+**
2. **Google Chrome** installed
3. **Google Cloud project** with Gmail API enabled
4. **OAuth 2.0 Desktop client** → download `credentials.json`
5. A WhatsApp account and the **exact chat/contact name** you want alerts sent to

## Gmail setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project → enable **Gmail API**.
3. Configure **OAuth consent screen** (External or Internal).
4. Create **OAuth client ID** → Application type: **Desktop app**.
5. Download JSON and save as `placement_notifier/credentials.json`.

**Gmail query used (strict):**

```
(is:unread from:cvr.placement@gmail.com) OR (is:unread from:alerts@haveloc.com)
```

Only emails matching this query are ever listed or fetched.

## WhatsApp Web setup (QR login, one time)

1. Copy `.env.example` to `.env`.
2. Set `WHATSAPP_CHAT_NAME` to the **exact** name shown in WhatsApp for your own chat or a saved contact (e.g. a chat titled with your name or “Placement Alerts”).
3. Install dependencies and run the app (see below).
4. On the **first** placement email (or when you trigger `POST /check` with a matching unread email), Chrome opens **WhatsApp Web**.
5. **Scan the QR code** with your phone (WhatsApp → Linked devices).
6. The session is saved under `data/chrome_whatsapp_profile` — you should **not** need to scan again unless you log out or delete that folder.

**Tips**

- Use the contact name exactly as it appears in the WhatsApp sidebar (case and spacing matter).
- Keep the Chrome window open while the notifier is running.
- Do not set `CHROME_HEADLESS=true`; WhatsApp Web often blocks headless browsers.
- Close other Chrome instances using the same profile path if the driver fails to start.

## Installation

```bash
cd placement_notifier
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set `WHATSAPP_CHAT_NAME`. Place `credentials.json` in the project folder.

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On first run, complete Gmail OAuth in the browser when prompted (`token.json` is saved).

When a placement email arrives, Chrome opens WhatsApp Web (if not already open), finds your chat by name, and sends the formatted alert.

## API

| Method | Path     | Description                        |
|--------|----------|------------------------------------|
| GET    | `/`      | Health check and last scan summary |
| POST   | `/check` | Manually trigger Gmail scan        |

Example:

```bash
curl http://localhost:8000/
curl -X POST http://localhost:8000/check
```

## Environment variables

| Variable                         | Description                                           |
|----------------------------------|-------------------------------------------------------|
| `WHATSAPP_CHAT_NAME`             | Exact WhatsApp contact/chat name to send messages to  |
| `CHROME_USER_DATA_DIR`           | Persistent Chrome profile (default: `data/chrome_whatsapp_profile`) |
| `WHATSAPP_LOGIN_TIMEOUT_SECONDS` | Max wait for QR login (default: 180)                  |
| `WHATSAPP_MAX_CHUNK_CHARS`       | Split long emails into multiple messages (default: 4000) |
| `GMAIL_CREDENTIALS_PATH`         | OAuth client JSON (default: `credentials.json`)       |
| `GMAIL_TOKEN_PATH`               | Saved Gmail token (default: `token.json`)             |
| `GMAIL_SCOPES`                   | Use `gmail.modify` to mark processed mail read        |
| `POLL_INTERVAL_SECONDS`          | Default: 30                                           |
| `STATE_FILE_PATH`                | Processed message IDs (default: `data/processed_ids.json`) |

## Security notes

- Never commit `.env`, `credentials.json`, `token.json`, or `data/chrome_whatsapp_profile/`.
- The Chrome profile contains your WhatsApp Web session — protect that directory.
- Run only on a machine you trust.

## License

MIT
