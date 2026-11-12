"""Parse monetary literals without relying on the model's arithmetic."""
import re
from decimal import Decimal, InvalidOperation

_BR = re.compile(r'[+-]?(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,[0-9]{1,2})?')
_DOT_DECIMAL = re.compile(r'[+-]?[0-9]+\.[0-9]{1,2}')


def parse_amount(value):
    # Numeric values already have an unambiguous decimal representation.
    if isinstance(value, bool):
        raise ValueError('Valor monetário inválido')
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith('R$'):
            text = text[2:].strip()
        if _BR.fullmatch(text):
            amount = Decimal(text.replace('.', '').replace(',', '.'))
        elif _DOT_DECIMAL.fullmatch(text):
            amount = Decimal(text)
        else:
            raise ValueError('Formato monetário inválido')
    else:
        raise ValueError('Valor monetário inválido')
    try:
        if not amount.is_finite() or amount != amount.quantize(Decimal('0.01')):
            raise ValueError('Valor monetário inválido')
    except InvalidOperation as exc:
        raise ValueError('Valor monetário inválido') from exc
    return amount


def amount_from_message(literal, message):
    if not isinstance(literal, str) or not literal.strip():
        raise ValueError('Valor original ausente')
    literal = literal.strip()
    # Do not accept a fabricated value or a fragment of a longer numeric token.
    pattern = r'(?<![\w.,+\-])' + re.escape(literal) + r'(?!\w|[.,][0-9])'
    if not re.search(pattern, message):
        raise ValueError('Valor original não encontrado na mensagem')
    return parse_amount(literal)
