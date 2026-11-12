import json
import os
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from app.llm import interpret_user_input
from app.money import amount_from_message, parse_amount
from app.utils import currency


class MoneyTests(unittest.TestCase):
    def test_brazilian_literals_and_numeric_values(self):
        cases = [('3.250', '3250'), ('12,50', '12.50'), ('3.250,90', '3250.90'),
                 ('R$ 3.250,90', '3250.90'), ('1.234.567,89', '1234567.89'),
                 ('3250', '3250'), ('0,50', '0.50'), ('12,5', '12.50'),
                 ('12.50', '12.50'), (' R$\u00a012,50 ', '12.50'),
                 (12.5, '12.50'), (Decimal('3.250'), '3.25')]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(parse_amount(value), Decimal(expected))

    def test_rejects_malformed_values_without_rounding(self):
        for value in ('', 'NaN', 'Infinity', True, None, '1,234.56', '12,345', '1.23.456',
                      '3k', 'doze', '1.2345', '12,', '1 000', '1e3', Decimal('1.234')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_amount(value)

    def test_original_literal_must_exist_as_a_whole_number(self):
        self.assertEqual(amount_from_message('12,50', 'Paguei 12,50.'), Decimal('12.50'))
        self.assertEqual(amount_from_message('R$ 3.250', 'Recebi R$ 3.250 de salário'), Decimal('3250'))
        for value, text in [('3250', 'Recebi 3.250'), ('250', 'Recebi 3.250'),
                            ('12', 'Gastei 12,50'), ('12,50', 'Gastei 12,500'),
                            ('50', 'Gastei -50'), ('10', 'Gastei 100')]:
            with self.subTest(value=value, text=text), self.assertRaises(ValueError):
                amount_from_message(value, text)

    def interpret(self, message, literal=None, numeric=None):
        data = dict(action='add_income', description='salário', date='2026-11-11')
        if literal is not None:
            data['amount_text'] = literal
        if numeric is not None:
            data['amount'] = numeric
        completion = Mock()
        completion.choices = [Mock()]
        completion.choices[0].message.content = json.dumps(data)
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test'}), patch('app.llm.Groq') as groq:
            groq.return_value.chat.completions.create.return_value = completion
            return interpret_user_input(message)

    def test_normalizes_literal_instead_of_trusting_model_arithmetic(self):
        action = self.interpret('Recebi 3.250 de salário', '3.250', numeric=3.25)
        self.assertEqual(action.action, 'add_income')
        self.assertEqual(action.amount, Decimal('3250'))
        self.assertEqual(currency(action.amount), 'R$ 3.250,00')
        self.assertNotIn('amount_text', action.model_dump())

    def test_missing_invented_invalid_or_nonpositive_amount_needs_clarification(self):
        cases = [('Recebi 3.250', None, 3.25), ('Recebi 3.250', '3250', None),
                 ('Recebi 12,345', '12,345', None), ('Recebi 0', '0', None),
                 ('Recebi -50', '-50', None), ('Recebi salário', None, 1000)]
        for message, literal, numeric in cases:
            with self.subTest(message=message):
                self.assertEqual(self.interpret(message, literal, numeric).action, 'clarify')
