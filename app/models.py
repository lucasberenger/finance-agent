from datetime import date as Date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['add_expense', 'add_income', 'summary', 'list', 'undo', 'clarify']
    description: str = Field(default='', max_length=300)
    category: str = Field(default='Não informado', max_length=100)
    source: str = Field(default='Não informado', max_length=100)
    payment_method: str = Field(default='Não informado', max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    date: Date | None = None
    month: Date | None = None
    limit: int = Field(default=5, ge=1, le=20)
    question: str = Field(default='Informe o valor e o que deseja registrar.', max_length=500)

    @model_validator(mode='after')
    def validate_entry(self):
        if self.action in ('add_expense', 'add_income'):
            if self.amount is None or not self.description.strip() or self.date is None:
                raise ValueError('Lançamento incompleto')
        return self
