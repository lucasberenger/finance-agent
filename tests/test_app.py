import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.actions import handle_action
from app.main import app, process_update
from app.models import Action
from app.llm import interpret_user_input
from app.sheets import SheetsRepository, parse_amount


class FakeRepository:
    def __init__(self):
        self.rows = []
        self.fail_after_add = False
        self.fail_after_undo = False

    def entries(self, owner):
        return list(self.rows)

    def add(self, action, owner, entry_id):
        if not any(r['id'] == entry_id for r in self.rows):
            self.rows.append(dict(kind=action.action, date=action.date, amount=action.amount,
                                  description=action.description, category=action.category,
                                  id=entry_id, created=entry_id.zfill(10), row=len(self.rows)))
        if self.fail_after_add:
            self.fail_after_add = False
            raise RuntimeError('Lost response after write')

    def undo(self, owner, operation_id, target=None):
        self.rows = [r for r in self.rows if r['id'] != target]
        if self.fail_after_undo:
            self.fail_after_undo = False
            raise RuntimeError('Lost response after undo')


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'STATE_DB_PATH': self.tmp.name + '/state.db',
                                         'TELEGRAM_BOT_TOKEN': 'test-token', 'TELEGRAM_OWNER_ID': '123', 'TELEGRAM_WEBHOOK_SECRET': 'secret'})
        self.env.start()
        self.repo = FakeRepository()
        self.repository_patch = patch('app.main.SheetsRepository', return_value=self.repo)
        self.repository_patch.start()

    def tearDown(self):
        self.repository_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def entry(self, amount='30.10', kind='add_expense', when='2026-10-31'):
        return Action(action=kind, description='Almoço', amount=amount, date=when, category='Alimentação')

    def test_interpretation_dates_and_invalid_output(self):
        from unittest.mock import Mock
        response = Mock()
        response.choices = [Mock()]
        with patch('app.llm.Groq') as groq, patch.dict(os.environ, {'GROQ_API_KEY': 'test'}), patch('app.llm.today', return_value=date(2026, 11, 8)):
            groq.return_value.chat.completions.create.return_value = response
            response.choices[0].message.content = '{"action":"add_expense","description":"almoço","amount_text":"30","date":"2026-11-07"}'
            action = interpret_user_input('Gastei 30 no almoço ontem')
            self.assertEqual(action.date, date(2026, 11, 7))
            messages = groq.return_value.chat.completions.create.call_args.kwargs['messages']
            self.assertIn('2026-11-08', messages[0]['content'])
            response.choices[0].message.content = '{"action":"add_expense","amount":30}'
            self.assertEqual(interpret_user_input('gastei').action, 'clarify')
            response.choices[0].message.content = 'invalid json'
            self.assertEqual(interpret_user_input('gastei').action, 'clarify')

    def test_validation(self):
        for amount in ('0', '-1', 'NaN', 'Infinity', '1.234'):
            with self.assertRaises(ValidationError):
                self.entry(amount)
        with self.assertRaises(ValidationError):
            Action(action='add_expense', amount=20)
        self.assertEqual(self.entry().payment_method, 'Não informado')

    def test_summary_period_and_decimal(self):
        self.repo.add(self.entry('0.10'), 123, '1')
        self.repo.add(self.entry('0.20'), 123, '2')
        self.repo.add(self.entry('10', 'add_income'), 123, '3')
        self.repo.add(self.entry('999', when='2026-11-01'), 123, '4')
        result = handle_action(Action(action='summary', month='2026-10-01'), self.repo, 123, '5')
        self.assertIn('Despesas: R$ 0,30', result)
        self.assertIn('Resultado do período: R$ 9,70', result)

    def test_retry_after_append_and_cached_response(self):
        self.repo.fail_after_add = True
        with patch('app.main.interpret_user_input', return_value=self.entry()) as interpret:
            with self.assertRaises(RuntimeError):
                process_update('1', 'gastei', 123)
            first = process_update('1', 'gastei', 123)
            self.assertEqual(first, process_update('1', 'gastei', 123))
            self.assertEqual(len(self.repo.rows), 1)
            interpret.assert_called_once()

    def test_undo_retry_does_not_undo_previous_entry(self):
        self.repo.add(self.entry(), 123, '1')
        self.repo.add(self.entry(), 123, '2')
        self.repo.fail_after_undo = True
        with patch('app.main.interpret_user_input', return_value=Action(action='undo')):
            with self.assertRaises(RuntimeError):
                process_update('3', 'desfazer', 123)
            process_update('3', 'desfazer', 123)
        self.assertEqual([r['id'] for r in self.repo.rows], ['1'])

    def test_last_entries(self):
        self.repo.add(self.entry(when='2026-11-01'), 123, '1')
        self.repo.add(self.entry(when='2026-10-01'), 123, '2')
        result = handle_action(Action(action='list', limit=1), self.repo, 123, '3')
        self.assertIn('01/11/2026', result)
        self.assertNotIn('01/10/2026', result)

    def test_webhook_access_and_removed_test_route(self):
        client = TestClient(app)
        payload = {'update_id': 1, 'message': {'chat': {'id': 123, 'type': 'private'},
                                              'from': {'id': 123}, 'text': '/resumo'}}
        self.assertEqual(client.post('/telegram/webhook', json=payload).status_code, 403)
        payload['message']['from']['id'] = 999
        self.assertEqual(client.post('/telegram/webhook', json=payload,
                         headers={'X-Telegram-Bot-Api-Secret-Token': 'secret'}).status_code, 403)
        self.assertEqual(client.post('/test', json={}).status_code, 404)

    def test_telegram_failure_returns_retry_without_duplicate(self):
        client = TestClient(app)
        payload = {'update_id': 1, 'message': {'chat': {'id': 123, 'type': 'private'},
                                              'from': {'id': 123}, 'text': 'gastei'}}
        headers = {'X-Telegram-Bot-Api-Secret-Token': 'secret'}
        from unittest.mock import AsyncMock
        with patch('app.main.interpret_user_input', return_value=self.entry()), patch(
                'app.main.httpx.AsyncClient.post', new_callable=AsyncMock) as post:
            post.side_effect = RuntimeError('offline')
            self.assertEqual(client.post('/telegram/webhook', json=payload, headers=headers).status_code, 503)
            post.side_effect = None
            import httpx
            post.return_value = httpx.Response(200, json={'ok': True})
            self.assertEqual(client.post('/telegram/webhook', json=payload, headers=headers).status_code, 200)
            self.assertEqual(len(self.repo.rows), 1)

    def test_legacy_and_metadata_rows(self):
        from unittest.mock import Mock
        expense = Mock(title='Saída')
        expense.get_all_values.return_value = [
            ['Data', 'Descrição', 'Categoria', 'Valor', 'Pagamento'],
            ['31/10/2026', 'Mercado', 'Supermercado', '1.234,56', 'Pix'],
            ['01/11/2026', 'Novo', 'Lazer', '10', 'Pix', 'id', '123', 'now', 'active'],
            ['01/11/2026', 'Cancelado', 'Lazer', '10', 'Pix', 'id2', '123', 'now', 'void'],
            ['01/11/2026', 'Outro', 'Lazer', '10', 'Pix', 'id3', '999', 'now', 'active']]
        with patch('app.sheets.worksheets', return_value={'add_expense': expense}):
            records = SheetsRepository().entries(123)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]['amount'], Decimal('1234.56'))
            SheetsRepository().add(self.entry(), 123, 'id2')
            expense.append_row.assert_not_called()
            SheetsRepository().add(self.entry(), 123, 'id4')
            self.assertEqual(expense.append_row.call_args.kwargs['value_input_option'], 'RAW')
        self.assertEqual(parse_amount('10.50'), Decimal('10.50'))


if __name__ == '__main__':
    unittest.main()
