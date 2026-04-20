# 🤖 AI Financial Assistant (Telegram Bot)

![Version](https://img.shields.io/badge/version-1.0.0-blue)

An AI-powered financial assistant that allows users to track expenses and income using natural language via Telegram.

This project demonstrates how to build and deploy a real-world AI agent with LLM integration, API orchestration, and cloud deployment.

---

## 🚀 Features

* 💬 Natural language input (Portuguese)
* 🤖 LLM-powered intent detection and data extraction
* 📲 Telegram bot integration (webhook-based)
* 📊 Google Sheets as a lightweight database
* ⚡ FastAPI backend for request handling
* ☁️ Deployed in production (Render)

---

## 🧠 How It Works

1. User sends a message via Telegram
   Example:

   ```
   Gastei 30 reais com lanche
   ```

2. The backend receives the message via webhook

3. The LLM interprets the message and returns structured data:

   ```json
   {
     "action": "add_expense",
     "description": "lanche",
     "category": "lazer",
     "amount": 30,
     "payment_method": "débito"
   }
   ```

4. The system processes the action and stores the data in Google Sheets

5. The bot responds to the user:

   ```
   💸 Gasto registrado (lazer): R$ 30,00
   ```

---

## 🏗️ Architecture

```
Telegram → FastAPI (Webhook) → LLM → Actions → Google Sheets
                                ↓
                          Response Formatter
```

---

## 🛠️ Tech Stack

* Python
* FastAPI
* LLM (Groq / LLama)
* Google Sheets API (gspread)
* Telegram Bot API
* HTTPX
* Cloud Deployment (Render)

---

## ⚙️ Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

---

### 2. Install dependencies

```bash
uv sync
```

---

### 3. Environment variables

Create a `.env` file:

```
GROQ_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_token
GOOGLE_CREDENTIALS_JSON=your_json
SHEET_NAME=your_sheet_name
```

---

### 4. Run locally

```bash
uv run uvicorn app.main:app --reload
```

---

### 5. Expose with ngrok

```bash
ngrok http 8000
```

---

### 6. Set Telegram webhook

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-ngrok-url/telegram/webhook"
```

---

## 📦 Deployment

The application is deployed using Render.

Start command:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## 📌 Future Improvements

* 📊 Expense summary and analytics
* 🎙️ Voice message support (speech-to-text)
* 📈 Monthly reports
* 🧠 Smarter categorization

---


## 📄 License

MIT
