from app.sheets import income_sheet, outcome_sheet
from app.utils import format_label, get_current_date

def add_expense(
        date_str: str,
        description: str, 
        category: str,
        amount: float, 
        payment_method: str,
) -> dict:
    category = format_label(category)
    payment_method = format_label(payment_method)
    outcome_sheet.append_row([
        date_str,
        description,
        category,
        amount,
        payment_method
    ])
    return {
        "status": "success",
        "action": "add_expense",
        "amount": amount,
        "category": category
    }

def add_income(
        date_str: str,
        description: str,
        source: str,
        amount: float,
) -> dict:
    source = format_label(source)
    income_sheet.append_row([
        date_str,
        description,
        source,
        amount
    ])
    return {
        "status": "success",
        "action": "add_income",
        "amount": amount,
        "source": source
    }

def handle_action(data: dict):
    action = data.get("action")

    if not action:
        return {"error": "Missing action"}

    if action == "add_expense":
        return add_expense(
            date_str=get_current_date(),
            description=data.get("description", None),
            category=data.get("category"),
            amount=data.get("amount"),
            payment_method=data.get("payment_method", None)
        )
    
    elif action == "add_income":
        return add_income(
            date_str=get_current_date(),
            description=data.get("description", None),
            source=data.get("source"),
            amount=data.get("amount")
        )

    else:
        return {"error": f"Unknown action: {action}"}