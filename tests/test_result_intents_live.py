"""Opt-in regression evaluation against Groq; never accesses Sheets or Telegram."""
import json
import os
import unittest
from pathlib import Path

from dotenv import load_dotenv

from app.llm import interpret_user_input


@unittest.skipUnless(os.getenv('RUN_LIVE_EVALS') == '1', 'Avaliação real exige RUN_LIVE_EVALS=1')
class ResultIntentsLiveTests(unittest.TestCase):
    def test_remaining_money_and_bank_balance_are_distinguished(self):
        root = Path(__file__).resolve().parent.parent
        load_dotenv(root / '.env')
        cases = json.loads((root / 'tests/fixtures/result_intents.json').read_text())
        for case in cases:
            with self.subTest(text=case['text']):
                try:
                    action = interpret_user_input(case['text'])
                except Exception as exc:
                    # Keep SDK exception text/URLs out of test reports.
                    self.fail(f'Falha na avaliação: {type(exc).__name__}')
                for field, expected in case.items():
                    if field != 'text':
                        self.assertEqual(getattr(action, field), expected)
