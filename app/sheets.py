"""Keep legacy columns; append metadata after them. RAW prevents formula execution."""
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from app.observability import event, timed

import gspread
from google.oauth2.service_account import Credentials


@lru_cache
@timed('sheets_connect')
def worksheets():
    credentials = Credentials.from_service_account_info(
        json.loads(os.environ['GOOGLE_CLOUD_CREDENTIALS']),
        scopes=['https://www.googleapis.com/auth/spreadsheets'])
    book = gspread.authorize(credentials).open_by_key(os.environ['SHEET_ID'])
    return {'add_income': book.worksheet('Entrada'), 'add_expense': book.worksheet('Saída')}


def parse_amount(value):
    text = str(value).replace('R$', '').strip()
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    return Decimal(text)


class SheetsRepository:
    @timed('sheets_read')
    def entries(self, owner):
        records = []
        for kind, sheet in worksheets().items():
            base = 5 if kind == 'add_expense' else 4
            for row_number, row in enumerate(sheet.get_all_values()[1:], start=2):
                if not any(row):
                    continue
                row = row + [''] * max(0, base + 4 - len(row))
                # Legacy rows belong to the configured single owner, but cannot be undone.
                if row[base + 1] and row[base + 1] != str(owner):
                    continue
                if row[base + 3] == 'void':
                    continue
                try:
                    when = datetime.strptime(row[0], '%d/%m/%Y').date()
                    amount = parse_amount(row[3])
                    if not amount.is_finite() or amount <= 0:
                        raise ValueError('Invalid amount')
                except (ValueError, InvalidOperation, IndexError) as exc:
                    raise ValueError(f'Confira a linha {row_number} da aba {sheet.title}: data ou valor inválido.') from exc
                records.append(dict(kind=kind, date=when, description=row[1], category=row[2],
                                    amount=amount, id=row[base], created=row[base + 2],
                                    row=row_number, base=base))
        return records

    @timed('sheets_add')
    def add(self, action, owner, entry_id):
        sheet = worksheets()[action.action]
        base = 5 if action.action == 'add_expense' else 4
        # Check even void rows: retries must never recreate an undone entry.
        if any(len(row) > base and row[base] == entry_id for row in sheet.get_all_values()[1:]):
            event('sheet_entry_already_exists')
            return
        values = [action.date.strftime('%d/%m/%Y'), action.description,
                  action.category if action.action == 'add_expense' else action.source,
                  float(action.amount)]
        if action.action == 'add_expense':
            values.append(action.payment_method)
        from datetime import timezone
        values.extend([entry_id, str(owner), datetime.now(timezone.utc).isoformat(), 'active'])
        sheet.append_row(values, value_input_option='RAW')

    @timed('sheets_undo')
    def undo(self, owner, operation_id, target=None):
        # The target is persisted before mutation so retries cannot undo another row.
        records = self.entries(owner)
        entry = next((r for r in records if r['id'] == target), None)
        if entry:
            worksheets()[entry['kind']].update_cell(entry['row'], entry['base'] + 4, 'void')
        return entry
