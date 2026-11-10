import asyncio
import hmac
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from threading import Lock

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from app.actions import handle_action
from app.llm import interpret_user_input
from app.models import Action
from app.sheets import SheetsRepository

load_dotenv()
log = logging.getLogger(__name__)
process_lock = Lock()


def settings():
    required = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET', 'TELEGRAM_OWNER_ID',
                'GROQ_API_KEY', 'GOOGLE_CLOUD_CREDENTIALS', 'SHEET_ID', 'STATE_DB_PATH')
    if missing := [key for key in required if not os.getenv(key)]:
        raise RuntimeError('Configure: ' + ', '.join(missing))
    return int(os.environ['TELEGRAM_OWNER_ID'])


@contextmanager
def database():
    path = Path(os.environ['STATE_DB_PATH'])
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS updates (id TEXT PRIMARY KEY, action TEXT NOT NULL, target TEXT, response TEXT)')
    db.commit()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app):
    settings()
    with database():
        pass
    yield


app = FastAPI(lifespan=lifespan)


def process_update(update_id, text, owner):
    # One worker: serialize Sheets read/write operations and retain retry state.
    with process_lock, database() as db:
        existing = db.execute('SELECT action, target, response FROM updates WHERE id=?', (update_id,)).fetchone()
        if existing and existing[2] is not None:
            return existing[2]
        repo = SheetsRepository()
        if existing:
            action, target = Action.model_validate_json(existing[0]), existing[1]
        else:
            action = interpret_user_input(text)
            target = None
            if action.action == 'undo':
                candidates = [r for r in repo.entries(owner) if r['id']]
                if candidates:
                    target = max(candidates, key=lambda r: r['created'])['id']
            db.execute('INSERT INTO updates(id, action, target) VALUES (?, ?, ?)',
                       (update_id, action.model_dump_json(), target))
            db.commit()
        response = handle_action(action, repo, owner, update_id, target)
        db.execute('UPDATE updates SET response=? WHERE id=?', (response, update_id))
        db.commit()
        return response


@app.get('/health')
def health():
    return {'ok': True}


@app.post('/telegram/webhook')
async def telegram_webhook(request: Request):
    expected = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
    provided = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not expected or not hmac.compare_digest(expected, provided):
        raise HTTPException(403, 'Forbidden')
    try:
        data = await request.json()
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, 'Invalid JSON')
    if not isinstance(data, dict):
        raise HTTPException(400, 'Invalid update')
    message = data.get('message')
    if not isinstance(message, dict):
        return {'ok': True}
    owner = int(os.environ['TELEGRAM_OWNER_ID'])
    chat, sender = message.get('chat', {}), message.get('from', {})
    if chat.get('type') != 'private' or chat.get('id') != owner or sender.get('id') != owner:
        raise HTTPException(403, 'Forbidden')
    text = message.get('text')
    if not isinstance(text, str) or not text.strip():
        return {'ok': True}
    if not isinstance(data.get('update_id'), int):
        raise HTTPException(400, 'Missing update ID')
    if len(text) > 4000:
        raise HTTPException(400, 'Message too long')
    try:
        response = await asyncio.to_thread(process_update, str(data['update_id']), text, owner)
        # Telegram has a 4096-character limit; split long category summaries.
        async with httpx.AsyncClient(timeout=20) as client:
            for start in range(0, len(response), 4000):
                result = await client.post(
                    f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                    json={'chat_id': owner, 'text': response[start:start + 4000]})
                if result.status_code != 200 or not result.json().get('ok'):
                    raise RuntimeError('Telegram delivery failed')
    except Exception:
        # Do not log exception strings: HTTP errors may contain the bot token.
        log.error('Update processing or delivery failed; update_id=%s', data['update_id'])
        raise HTTPException(503, 'Temporary failure; retry update')
    return {'ok': True}
