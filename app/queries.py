"""Date filtering and financial answers are deterministic, independent of the LLM."""
from calendar import monthrange
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from app.utils import currency


def month_bounds(month):
    return month.replace(day=1), month.replace(day=monthrange(month.year, month.month)[1])


def summary(records, title):
    income = sum((r['amount'] for r in records if r['kind'] == 'add_income'), Decimal(0))
    expenses = sum((r['amount'] for r in records if r['kind'] == 'add_expense'), Decimal(0))
    categories = defaultdict(Decimal)
    for row in records:
        if row['kind'] == 'add_expense':
            categories[row['category']] += row['amount']
    lines = [title, f'Receitas: {currency(income)}', f'Despesas: {currency(expenses)}',
             f'Resultado do período: {currency(income - expenses)}']
    lines.extend(f'{key}: {currency(value)}' for key, value in
                 sorted(categories.items(), key=lambda item: -item[1]))
    return '\n'.join(lines)


def answer_query(action, records):
    reference = action.query_date
    if action.period in ('today', 'yesterday'):
        day = reference - timedelta(days=1) if action.period == 'yesterday' else reference
        start, end = day, day
        label = f"{'ontem' if action.period == 'yesterday' else 'hoje'} ({day:%d/%m/%Y})"
    else:
        start, end = month_bounds(action.month if action.period == 'month' else reference)
        label = f'em {start:%m/%Y}'
    records = [r for r in records if start <= r['date'] <= end]
    if action.metric == 'summary':
        return summary(records, f'Resumo {label}')
    income = sum((r['amount'] for r in records if r['kind'] == 'add_income'), Decimal(0))
    expenses = sum((r['amount'] for r in records if r['kind'] == 'add_expense'), Decimal(0))
    if action.metric == 'expenses':
        return f'Você gastou {currency(expenses)} {label}.'
    if action.metric == 'income':
        return f'Você recebeu {currency(income)} {label}.'
    result = income - expenses
    if not records:
        return f'Não há receitas ou despesas registradas {label}. Resultado: {currency(0)}.'
    prefix = f'Pelos lançamentos registrados {label}, '
    if result > 0:
        return prefix + f'sobraram {currency(result)}.'
    if result < 0:
        return prefix + f'as despesas superaram as receitas em {currency(-result)}.'
    return prefix + f'as receitas e despesas ficaram equilibradas. Resultado: {currency(0)}.'
