from app.utils import currency, today
from app.queries import answer_query, summary


def handle_action(action, repo, owner, operation_id, target=None):
    if action.action == 'clarify':
        return action.question
    if action.action in ('add_expense', 'add_income'):
        repo.add(action, owner, operation_id)
        label = 'Gasto' if action.action == 'add_expense' else 'Receita'
        detail = action.category if action.action == 'add_expense' else action.source
        payment = f'\nPagamento: {action.payment_method}' if action.action == 'add_expense' else ''
        return (f'{label} registrado: {currency(action.amount)}\n{action.description} — {detail}'
                f'\nData: {action.date:%d/%m/%Y}{payment}\n/desfazer para cancelar o último lançamento.')
    if action.action == 'undo':
        repo.undo(owner, operation_id, target)
        return 'Último lançamento desfeito.' if target else 'Nenhum lançamento novo disponível para desfazer.'
    records = repo.entries(owner)
    if action.action == 'query':
        return answer_query(action, records)
    if action.action == 'summary':
        month = action.month or today()
        records = [r for r in records if (r['date'].year, r['date'].month) == (month.year, month.month)]
        return summary(records, f'Resumo de {month:%m/%Y}')
    if action.month:
        records = [r for r in records if (r['date'].year, r['date'].month) == (action.month.year, action.month.month)]
    records.sort(key=lambda r: (r['date'], r['created'], r['row']), reverse=True)
    if not records:
        return 'Nenhum lançamento encontrado.'
    return '\n'.join(f"{r['date']:%d/%m/%Y} | {'−' if r['kind'] == 'add_expense' else '+'}{currency(r['amount'])} | {r['description']}" for r in records[:action.limit])
