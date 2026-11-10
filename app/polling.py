"""Recebimento local de mensagens do Telegram durante o desenvolvimento."""
# TEMPORÁRIO: este polling será substituído pelo webhook público no futuro.
# O encaminhamento reutiliza a rota local e suas validações, sem duplicar ações.
import argparse
import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.observability import configure_logging, context, event, stage


class TelegramPoller:
    def __init__(self, token, owner, secret, server_url='http://127.0.0.1:8000'):
        self.base = 'https://api.telegram.org/bot' + token
        self.owner = owner
        self.secret = secret
        self.server_url = server_url.rstrip('/')
        self.offset = None

    def check(self, telegram, local):
        with stage('polling_startup'):
            local.get(self.server_url + '/health').raise_for_status()
            result = telegram.get(self.base + '/getWebhookInfo')
            result.raise_for_status()
            data = result.json()
            if not data.get('ok'):
                raise ValueError('Telegram recusou a consulta')
            if data['result'].get('url'):
                raise ValueError('Há webhook ativo; polling não iniciado')

    def poll_once(self, telegram, local):
        params = {'timeout': 25, 'allowed_updates': '["message"]'}
        if self.offset is not None:
            params['offset'] = self.offset
        result = telegram.get(self.base + '/getUpdates', params=params)
        result.raise_for_status()
        data = result.json()
        if not data.get('ok'):
            raise ValueError('Telegram recusou a consulta')
        for update in data['result']:
            message = update.get('message') or {}
            chat, sender = message.get('chat') or {}, message.get('from') or {}
            if (sender.get('id') == self.owner and chat.get('id') == self.owner
                    and chat.get('type') == 'private' and message.get('text')):
                with context(update_id=str(update['update_id'])), stage('polling_forward'):
                    response = local.post(
                        self.server_url + '/telegram/webhook', json=update,
                        headers={'X-Telegram-Bot-Api-Secret-Token': self.secret})
                    response.raise_for_status()
            # Confirm only after successful handling. Failures leave this update pending.
            self.offset = update['update_id'] + 1

    def run(self):
        with httpx.Client(timeout=40) as telegram, httpx.Client(timeout=180) as local:
            self.check(telegram, local)
            event('polling_started')
            while True:
                try:
                    self.poll_once(telegram, local)
                except (httpx.HTTPError, ValueError) as exc:
                    status = getattr(getattr(exc, 'response', None), 'status_code', None)
                    # Invalid credentials or concurrent receivers need operator intervention.
                    if isinstance(exc, httpx.HTTPStatusError) and status in (401, 403, 409):
                        event('polling_stopped', level=logging.ERROR,
                              reason='authentication_or_receiver_conflict', status_code=status)
                        return 1
                    event('polling_retry', level=logging.WARNING,
                          error_type=type(exc).__name__, status_code=status)
                    time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='Polling temporário para testar o bot localmente.')
    parser.add_argument('--server-url', default='http://127.0.0.1:8000',
                        help='Endereço do servidor FastAPI local')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    configure_logging()
    try:
        required = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_OWNER_ID', 'TELEGRAM_WEBHOOK_SECRET')
        if any(not os.getenv(key) for key in required):
            event('polling_stopped', level=logging.ERROR, reason='missing_configuration')
            return 1
        poller = TelegramPoller(os.environ['TELEGRAM_BOT_TOKEN'],
                                int(os.environ['TELEGRAM_OWNER_ID']),
                                os.environ['TELEGRAM_WEBHOOK_SECRET'], args.server_url)
        return poller.run()
    except KeyboardInterrupt:
        event('polling_stopped', reason='interrupted')
        return 0
    except Exception as exc:
        # Exception messages/URLs can contain credentials. Never print raw exceptions.
        event('polling_stopped', level=logging.ERROR, error_type=type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
