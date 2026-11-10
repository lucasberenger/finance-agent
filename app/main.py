import asyncio
import hmac
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
from app.observability import configure_logging, context, event, stage
from app.sheets import SheetsRepository

load_dotenv()
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
    configure_logging()
    with stage('startup'):
        settings()
        with database():
            pass
    event('application_started')
    try:
        yield
    finally:
        event('application_stopped')


app = FastAPI(lifespan=lifespan)


def process_update(update_id, text, owner):
    with context(update_id=update_id), stage('processing'):
        return _process_update(update_id, text, owner)


def _process_update(update_id, text, owner):
    # One worker: serialize Sheets read/write operations and retain retry state.
    with process_lock, database() as db:
        with stage('journal_read'):
            existing = db.execute('SELECT action, target, response FROM updates WHERE id=?', (update_id,)).fetchone()
        if existing and existing[2] is not None:
            event('update_replayed')
            return existing[2]
        repo = SheetsRepository()
        if existing:
            action, target = Action.model_validate_json(existing[0]), existing[1]
            event('update_resumed', action=action.action)
        else:
            with stage('interpretation'):
                action = interpret_user_input(text)
            target = None
            if action.action == 'undo':
                candidates = [r for r in repo.entries(owner) if r['id']]
                if candidates:
                    target = max(candidates, key=lambda r: r['created'])['id']
            with stage('journal_save_action'):
                db.execute('INSERT INTO updates(id, action, target) VALUES (?, ?, ?)',
                           (update_id, action.model_dump_json(), target))
                db.commit()
        with context(action=action.action):
            event('action_selected')
            with stage('action'):
                response = handle_action(action, repo, owner, update_id, target)
            with stage('journal_save_response'):
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
        event('webhook_rejected', reason='invalid_secret', status_code=403)
        raise HTTPException(403, 'Forbidden')
    try:
        data = await request.json()
    except (ValueError, UnicodeDecodeError):
        event('webhook_rejected', reason='invalid_json', status_code=400)
        raise HTTPException(400, 'Invalid JSON')
    if not isinstance(data, dict):
        event('webhook_rejected', reason='invalid_update', status_code=400)
        raise HTTPException(400, 'Invalid update')
    message = data.get('message')
    if not isinstance(message, dict):
        event('webhook_ignored', reason='unsupported_update')
        return {'ok': True}
    owner = int(os.environ['TELEGRAM_OWNER_ID'])
    chat, sender = message.get('chat') or {}, message.get('from') or {}
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        event('webhook_rejected', reason='invalid_sender', status_code=400)
        raise HTTPException(400, 'Invalid sender')
    if chat.get('type') != 'private' or chat.get('id') != owner or sender.get('id') != owner:
        event('webhook_rejected', reason='unauthorized_sender', status_code=403)
        raise HTTPException(403, 'Forbidden')
    text = message.get('text')
    if not isinstance(text, str) or not text.strip():
        event('webhook_ignored', reason='no_text')
        return {'ok': True}
    if not isinstance(data.get('update_id'), int):
        event('webhook_rejected', reason='missing_update_id', status_code=400)
        raise HTTPException(400, 'Missing update ID')
    if len(text) > 4000:
        event('webhook_rejected', reason='message_too_long', status_code=400)
        raise HTTPException(400, 'Message too long')
    with context(update_id=str(data['update_id'])):
        event('webhook_received')
        try:
            with stage('webhook'):
                response = await asyncio.to_thread(process_update, str(data['update_id']), text, owner)
                # Telegram has a 4096-character limit; split long category summaries.
                with stage('telegram_send'):
                    async with httpx.AsyncClient(timeout=20) as client:
                        for start in range(0, len(response), 4000):
                            result = await client.post(
                                f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                                json={'chat_id': owner, 'text': response[start:start + 4000]})
                            if result.status_code != 200 or not result.json().get('ok'):
                                event('telegram_delivery_rejected', status_code=result.status_code)
                                raise RuntimeError('Telegram delivery failed')
        except Exception:
            event('webhook_retry_required', status_code=503)
            raise HTTPException(503, 'Temporary failure; retry update') from None
        event('webhook_completed', status_code=200)
    return {'ok': True}
