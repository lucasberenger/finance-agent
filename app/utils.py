from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo


def today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()


def currency(value):
    return 'R$ ' + f'{Decimal(str(value)):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
