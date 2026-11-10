import asyncio
import io
import json
import logging
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.observability import JsonFormatter, configure_logging, context, event, stage


class ObservabilityTests(unittest.TestCase):
    def formatted(self, records):
        return [json.loads(JsonFormatter().format(record)) for record in records]

    def test_context_and_failure_do_not_log_sensitive_data(self):
        private = 'TOKEN-SECRETO almoço R$ 3250 cpf email@example.com'
        with self.assertLogs('app.events', level='INFO') as logs:
            with context(update_id='42'):
                with self.assertRaises(httpx.HTTPStatusError):
                    with stage('telegram_send'):
                        request = httpx.Request('POST', 'https://api.telegram.org/bot' + private.replace(' ', '-') + '/sendMessage')
                        raise httpx.HTTPStatusError(private, request=request, response=httpx.Response(401))
            event('outside', message=private, token=private, amount=3250)
        data = self.formatted(logs.records)
        self.assertEqual(data[0]['update_id'], '42')
        self.assertEqual(data[0]['stage'], 'telegram_send')
        self.assertEqual(data[0]['error_type'], 'HTTPStatusError')
        self.assertEqual(data[0]['status_code'], 401)
        self.assertGreaterEqual(data[0]['duration_ms'], 0)
        self.assertNotIn('update_id', data[1])
        rendered = json.dumps(data)
        self.assertNotIn(private, rendered)
        self.assertNotIn('TOKEN-SECRETO', rendered)
        self.assertNotIn('amount', rendered)

    def test_context_survives_to_thread_and_is_isolated(self):
        async def worker(update_id):
            with context(update_id=update_id):
                await asyncio.sleep(0)
                await asyncio.to_thread(event, 'thread_event')
        async def run():
            await asyncio.gather(worker('1'), worker('2'))
        with self.assertLogs('app.events', level='INFO') as logs:
            asyncio.run(run())
        self.assertEqual({r['update_id'] for r in self.formatted(logs.records)}, {'1', '2'})

    def test_configuration_is_idempotent_and_sdk_logging_is_silent(self):
        names = ['app', 'httpx', 'httpcore', 'groq', 'google', 'urllib3', 'gspread']
        old = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).level,
                      logging.getLogger(name).propagate) for name in names}
        stream = io.StringIO()
        try:
            with patch.dict('os.environ', {'LOG_LEVEL': 'INFO'}), patch('app.observability.sys.stdout', stream):
                configure_logging()
                configure_logging()
                event('test_event')
                logging.getLogger('httpx').info('https://api.telegram.org/botSECRET/sendMessage')
            lines = stream.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])['event'], 'test_event')
            self.assertNotIn('SECRET', stream.getvalue())
        finally:
            for name, (handlers, level, propagate) in old.items():
                logger = logging.getLogger(name)
                logger.handlers, logger.level, logger.propagate = handlers, level, propagate

    def test_delivery_failure_has_stage_id_and_no_payload(self):
        env = {'TELEGRAM_OWNER_ID': '123', 'TELEGRAM_WEBHOOK_SECRET': 'test-secret',
               'TELEGRAM_BOT_TOKEN': 'test-token'}
        payload = {'update_id': 42, 'message': {'chat': {'id': 123, 'type': 'private'},
                   'from': {'id': 123}, 'text': 'Recebi R$ 3.250 de cliente privado'}}
        with patch.dict('os.environ', env), patch('app.main.process_update', return_value='Resposta privada'), patch(
                'app.main.httpx.AsyncClient.post', new_callable=AsyncMock, side_effect=RuntimeError('test-token Resposta privada')):
            with self.assertLogs('app.events', level='INFO') as logs:
                response = TestClient(app).post('/telegram/webhook', json=payload,
                    headers={'X-Telegram-Bot-Api-Secret-Token': 'test-secret'})
        self.assertEqual(response.status_code, 503)
        events = self.formatted(logs.records)
        failure = next(row for row in events if row.get('stage') == 'telegram_send')
        self.assertEqual(failure['update_id'], '42')
        self.assertEqual(failure['event'], 'stage_failed')
        output = json.dumps(events)
        for secret in ('test-token', 'test-secret', 'Resposta privada', payload['message']['text']):
            self.assertNotIn(secret, output)

    def test_invalid_llm_output_emits_warning_without_response(self):
        from unittest.mock import Mock
        from app.llm import interpret_user_input
        result = Mock()
        result.choices = [Mock()]
        result.choices[0].message.content = 'private invalid output'
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test'}), patch('app.llm.Groq') as groq:
            groq.return_value.chat.completions.create.return_value = result
            with self.assertLogs('app.events', level='INFO') as logs:
                action = interpret_user_input('private user message')
        self.assertEqual(action.action, 'clarify')
        events = self.formatted(logs.records)
        self.assertIn('llm_output_invalid', [row['event'] for row in events])
        self.assertNotIn('private', json.dumps(events))
