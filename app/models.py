from datetime import date as Date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils import today


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['add_expense', 'add_income', 'summary', 'query', 'list', 'undo', 'clarify']
    description: str = Field(default='', max_length=300)
    category: str = Field(default='Não informado', max_length=100)
    source: str = Field(default='Não informado', max_length=100)
    payment_method: str = Field(default='Não informado', max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    date: Date | None = None
    month: Date | None = None
    metric: Literal['expenses', 'income', 'result', 'summary'] | None = None
    period: Literal['current_month', 'today', 'yesterday', 'month'] = 'current_month'
    query_date: Date | None = None
    limit: int = Field(default=5, ge=1, le=20)
    question: str = Field(default='Informe o valor e o que deseja registrar.', max_length=500)

    @model_validator(mode='after')
    def validate_entry(self):
        if self.action in ('add_expense', 'add_income'):
            if self.amount is None or not self.description.strip() or self.date is None:
                raise ValueError('Lançamento incompleto')
        if self.action == 'query':
            if self.metric is None:
                raise ValueError('Consulta precisa de uma métrica')
            if self.period == 'month' and self.month is None:
                raise ValueError('Informe o mês da consulta')
            if self.period != 'month' and self.month is not None:
                raise ValueError('Mês incompatível com o período')
            if self.amount is not None or self.date is not None:
                raise ValueError('Consulta não recebe dados de lançamento')
            # Freeze relative dates before saving to the journal, including retries after midnight.
            self.query_date = self.query_date or today()
        return self
