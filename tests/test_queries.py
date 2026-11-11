import json
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.actions import handle_action
from app.llm import interpret_user_input
from app.main import process_update
from app.models import Action
from app.queries import month_bounds


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.entries.return_value = [
            self.row('add_income', '3250', date(2026, 11, 10)),
            self.row('add_expense', '12.50', date(2026, 11, 10)),
            self.row('add_expense', '30', date(2026, 11, 9)),
            self.row('add_income', '100', date(2026, 10, 31)),
            self.row('add_expense', '80', date(2026, 10, 31)),
            self.row('add_expense', '999', date(2026, 12, 1)),
        ]

    def row(self, kind, amount, when):
        return dict(kind=kind, amount=Decimal(amount), date=when, category='Alimentação')

    def query(self, metric='expenses', **kwargs):
        return Action(action='query', metric=metric, query_date=date(2026, 11, 10), **kwargs)

    def answer(self, action):
        result = handle_action(action, self.repo, 123, 'test-query')
        self.repo.add.assert_not_called()
        self.repo.undo.assert_not_called()
        return result

    def test_default_month_only_answers_requested_metric(self):
        self.assertEqual(self.answer(self.query()), 'Você gastou R$ 42,50 em 11/2026.')
        self.assertEqual(self.answer(self.query('income')), 'Você recebeu R$ 3.250,00 em 11/2026.')
        self.assertEqual(self.answer(self.query('result')),
                         'Pelos lançamentos registrados em 11/2026, sobraram R$ 3.207,50.')

    def test_today_and_yesterday(self):
        self.assertEqual(self.answer(self.query(period='today')),
                         'Você gastou R$ 12,50 hoje (10/11/2026).')
        self.assertEqual(self.answer(self.query(period='yesterday')),
                         'Você gastou R$ 30,00 ontem (09/11/2026).')
        self.assertEqual(self.answer(self.query('income', period='yesterday')),
                         'Você recebeu R$ 0,00 ontem (09/11/2026).')

    def test_explicit_month_and_full_summary(self):
        self.assertEqual(self.answer(self.query(period='month', month='2026-10-01')),
                         'Você gastou R$ 80,00 em 10/2026.')
        answer = self.answer(self.query('summary', period='today'))
        for text in ('Receitas: R$ 3.250,00', 'Despesas: R$ 12,50',
                     'Resultado do período: R$ 3.237,50', 'Alimentação: R$ 12,50'):
            self.assertIn(text, answer)

    def test_empty_period_and_negative_result(self):
        self.assertIn('despesas superaram as receitas em R$ 30,00',
                      self.answer(self.query('result', period='yesterday')))
        self.repo.entries.return_value = []
        self.assertEqual(self.answer(self.query()), 'Você gastou R$ 0,00 em 11/2026.')
        self.assertEqual(self.answer(self.query('result')),
                         'Não há receitas ou despesas registradas em 11/2026. Resultado: R$ 0,00.')

    def test_result_is_based_on_registered_entries_not_bank_balance(self):
        self.repo.entries.return_value = [self.row('add_income', '3250', date(2026, 11, 10)),
                                         self.row('add_expense', '12.50', date(2026, 11, 10))]
        self.assertEqual(self.answer(self.query('result')),
                         'Pelos lançamentos registrados em 11/2026, sobraram R$ 3.237,50.')
        self.repo.entries.return_value = [self.row('add_income', '12.50', date(2026, 11, 10)),
                                         self.row('add_expense', '12.50', date(2026, 11, 10))]
        self.assertEqual(self.answer(self.query('result', period='today')),
                         'Pelos lançamentos registrados hoje (10/11/2026), as receitas e despesas ficaram equilibradas. Resultado: R$ 0,00.')

    def test_month_boundary_and_leap_year(self):
        self.assertEqual(month_bounds(date(2024, 2, 15)), (date(2024, 2, 1), date(2024, 2, 29)))
        self.repo.entries.return_value = [self.row('add_expense', '0.10', date(2025, 12, 31)),
                                         self.row('add_expense', '0.20', date(2025, 12, 31)),
                                         self.row('add_expense', '100', date(2026, 1, 1))]
        action = Action(action='query', metric='expenses', period='yesterday', query_date='2026-01-01')
        self.assertEqual(self.answer(action), 'Você gastou R$ 0,30 ontem (31/12/2025).')

    def test_rejects_incomplete_or_conflicting_query(self):
        for fields in ({}, {'metric': 'unknown'}, {'metric': 'expenses', 'period': 'month'},
                       {'metric': 'expenses', 'period': 'today', 'month': '2026-11-01'},
                       {'metric': 'expenses', 'amount': 10}, {'metric': 'expenses', 'date': '2026-11-10'}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Action(action='query', **fields)

    def test_relative_dates_are_preserved_when_reloading_journal(self):
        with patch('app.models.today', return_value=date(2026, 11, 10)):
            action = Action(action='query', metric='expenses', period='yesterday')
        with patch('app.models.today', return_value=date(2026, 11, 11)):
            restored = Action.model_validate_json(action.model_dump_json())
        self.assertEqual(restored.query_date, date(2026, 11, 10))
        self.assertIn('09/11/2026', self.answer(restored))

    def test_interpreter_accepts_query_and_keeps_summary_command(self):
        result = Mock()
        result.choices = [Mock()]
        result.choices[0].message.content = json.dumps({'action': 'query', 'metric': 'expenses', 'period': 'today'})
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test'}), patch('app.llm.Groq') as groq:
            groq.return_value.chat.completions.create.return_value = result
            action = interpret_user_input('Quanto gastei hoje?')
            self.assertEqual((action.action, action.metric, action.period), ('query', 'expenses', 'today'))
            self.assertEqual(interpret_user_input('/resumo').action, 'summary')
            groq.return_value.chat.completions.create.assert_called_once()
            result.choices[0].message.content = '{"action":"query"}'
            self.assertEqual(interpret_user_input('quanto gastei?').action, 'clarify')

    def test_processing_query_does_not_write_financial_records(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'STATE_DB_PATH': folder + '/state.db'}), patch(
                'app.main.SheetsRepository', return_value=self.repo), patch(
                'app.main.interpret_user_input', return_value=self.query()) as interpret:
            first = process_update('query-1', 'quanto gastei?', 123)
            self.assertEqual(first, process_update('query-1', 'quanto gastei?', 123))
            interpret.assert_called_once()
            self.repo.entries.assert_called_once_with(123)
        self.repo.add.assert_not_called()
        self.repo.undo.assert_not_called()
