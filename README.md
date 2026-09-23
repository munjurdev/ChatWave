# 💬 ChatWave

**ChatWave** is a real-time messaging platform built with Django and WebSockets — fast, private, and reliable. Chat right in your browser: private chats, group chats, voice notes, file sharing, emoji reactions, and read receipts, all wrapped in a polished dark/light themed UI.

![Tech](https://img.shields.io/badge/Django-6.0-44B78B?logo=django&logoColor=white)
![Tech](https://img.shields.io/badge/Channels-4.2-00A884)
![Tech](https://img.shields.io/badge/Redis-Required-DC382D?logo=redis&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)

---

## ✨ Features

| | |
|---|---|
| ⚡ **Real-time messaging** | Instant delivery over persistent WebSocket connections (Django Channels + Redis) |
| 👤 **Private chats** | One-to-one conversations with online status indicators |
| 👥 **Group chats** | Create groups, add/remove members with admin controls |
| 🎤 **Voice notes** | Record voice messages with a live timer, right from the input bar |
| 📎 **File sharing** | Send files up to 10MB with image previews |
| 😀 **Reactions** | React to messages: ❤️ 😂 😮 😢 😡 👍 |
| ✔️ **Read receipts** | Single tick (sent) → double tick (delivered) → blue tick (read) |
| ✍️ **Typing indicators** | See when the other person is typing |
| 🔒 **Privacy & safety** | Email verification, user blocking, and reporting |
| 🌓 **Themes** | Carefully crafted dark & light modes |
| 📱 **Responsive** | Works on desktop, tablet, and mobile |
| 🔗 **SEO & sharing** | Open Graph + Twitter Card previews on every page |

## 🌐 Pages

| URL | Description |
|-----|-------------|
| `/` | Marketing landing page |
| `/app/` | Chat application |
| `/api/login/` | Sign in / Sign up / Password reset |
| `/info/news/` | News & updates |
| `/info/features/` | Platform features |
| `/info/careers/` | Careers |
| `/info/help/` | Help Center |
| `/admin/` | Django admin panel |
| `/api/` | REST API endpoints |

## 🛠️ Tech Stack

- **Backend:** Django 6.0, Django REST Framework, Channels 4 (ASGI/Daphne)
- **Auth:** SimpleJWT (access/refresh tokens), email OTP verification
- **Real-time:** Channels Redis channel layer, WebSocket consumers
- **Database:** SQLite (dev) / PostgreSQL-ready
- **Frontend:** Vanilla JS + WebSocket API, no build step required

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.13+**
- **Redis** running on `127.0.0.1:6379` (required for WebSockets)
  - Windows: use [Memurai](https://www.memurai.com/), WSL (`sudo apt install redis-server`), or Docker: `docker run -p 6379:6379 redis`
  - macOS: `brew install redis && redis-server`
  - Linux: `sudo apt install redis-server`

### 1. Clone the repository

```bash
git clone https://github.com/munjurdev/ChatWave.git
cd ChatWave
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows (Git Bash / PowerShell)
venv/Scripts/python.exe -m pip install -r requirements.txt

# macOS / Linux
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Email (SMTP) — used for OTP verification & password reset
EMAIL_USE_SSL=True
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_PORT=465
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend

# CORS (comma-separated origins your frontend runs on)
CORS_ALLOWED_ORIGINS=http://localhost:8000
CSRF_TRUSTED_ORIGINS=http://localhost:8000

# Public site URL (used for Open Graph links)
SITE_URL=http://127.0.0.1:8000
```

> 💡 Generate a Django secret key:
> ```bash
> python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
> ```

### 4. Run migrations

```bash
venv/Scripts/python.exe manage.py migrate
```

### 5. Start Redis

Make sure Redis is running on port `6379` before starting the server (see Prerequisites).

### 6. Run the development server

```bash
venv/Scripts/python.exe manage.py runserver
```

The app is now live at **http://127.0.0.1:8000** 🎉

> ℹ️ This project uses **ASGI/Daphne** — `runserver` automatically serves HTTP + WebSockets.

### 7. Create a superuser (optional)

```bash
venv/Scripts/python.exe manage.py createsuperuser
```

Access the admin panel at http://127.0.0.1:8000/admin/

---

## 🔌 WebSocket Endpoints

| Endpoint | Purpose |
|----------|---------|
| `ws/chat/list/?token=<JWT>` | Chat list updates (new messages, unread counts, presence) |
| `ws/chat/<chat_id>/?token=<JWT>` | Active chat (messages, typing, read receipts, reactions) |

## 📡 Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/sign-up` | Register (sends OTP) |
| `POST` | `/api/auth/verify-email` | Verify email with OTP |
| `POST` | `/api/auth/sign-in` | Get JWT tokens |
| `GET/POST` | `/api/chats` | List / create chats |
| `GET/POST` | `/api/chats/<id>/messages` | Fetch / send messages |
| `GET/PATCH` | `/api/me` | Profile management |

*Full API list available in `chat/urls.py` and `accounts/urls.py`.*

---

## 📁 Project Structure

```
ChatWave/
├── accounts/          # User model, auth API (JWT, OTP, blocking, reports)
├── chat/              # Chat app: models, consumers, serializers, templates
│   ├── consumers.py   # WebSocket consumers (list + chat)
│   ├── templates/     # UI: landing, auth, chatwave, info pages
│   └── routing.py     # WebSocket URL routing
├── core/              # Settings, ASGI, URLs, context processors
├── static/            # Favicon, OG image
└── media/             # User uploads (avatars, files, voice notes)
```

## 🧪 Development Notes

- The UI uses **no build tools** — templates contain vanilla JS, edit and refresh.
- JWT access tokens live 10 days; refresh tokens 30 days (see `SIMPLE_JWT` in `core/settings.py`).
- Message size limit: **10MB** per file/voice note.
- Channels uses the **Redis channel layer** — without Redis, HTTP works but WebSockets won't connect.

## 📄 License

© 2026 ChatWave. All rights reserved.

Designed & Developed by **[Munjur Alom](https://github.com/munjurdev)**
