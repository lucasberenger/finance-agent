"""Opt-in format evaluation; no financial writes or Telegram messages."""
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from app.llm import interpret_user_input


@unittest.skipUnless(os.getenv('RUN_LIVE_EVALS') == '1', 'Avaliação real exige RUN_LIVE_EVALS=1')
class BrazilianAmountsLiveTests(unittest.TestCase):
    def test_amount_formats(self):
        root = Path(__file__).resolve().parent.parent
        load_dotenv(root / '.env')
        for case in json.loads((root / 'tests/fixtures/brazilian_amounts.json').read_text()):
            with self.subTest(text=case['text']):
                try:
                    action = interpret_user_input(case['text'])
                except Exception as exc:
                    self.fail(f'Falha na avaliação: {type(exc).__name__}')
                self.assertEqual(action.action, case['action'])
                if 'amount' in case:
                    self.assertEqual(action.amount, Decimal(case['amount']))
