from actions import handle_action

response = handle_action({
    "action": "add_expense",
    "amount": 10,
    "category": "Lanche",
    "description": "Mc Donald's",
    "payment_method": "Débito",
    "date_str": "2026-04-14"
})

print(response)