# Custom util functions
from datetime import datetime
from zoneinfo import ZoneInfo

def format_label(text: str) -> str:
    if not text:
        return text

    words = text.split()
    return " ".join([w.capitalize() for w in words])

def format_message(action: str, amount: float | int | None, category: str | None = None) -> str:
    """Format the message to send it to the user"""
    def _format_currency(value):
        if value is None:
            return ""
        return f"{value:.2f}".replace(".", ",")
    
    category_text = f" ({category})" if category else ""
    match action:
        case "add_expense":
            return f"💸 Gasto registrado{category_text}: R$ {_format_currency(amount)}"
        case "add_income":
            return f"💰 Receita registrada{category_text}: R$ {_format_currency(amount)}"
        case "error":
            return "⚠️ Não consegui entender. Tente novamente."
        case _:
            return "✅ Ok"
        
def get_current_date() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
