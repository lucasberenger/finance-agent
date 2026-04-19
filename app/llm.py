from groq import Groq
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT = """
You are a financial AI agent.

Your task is to extract structured financial data from user messages.

You MUST return ONLY valid JSON. No explanations.

------------------------
AVAILABLE ACTIONS:
- add_expense: when the user spends money
- add_income: when the user receives money

------------------------
RULES:

1. Always return one of these JSON formats:

- if action is add_expense:
{
  "action": "add_expense",
  "description": string,
  "category": string,
  "amount": number,
  "payment_method": string
}

- if action is add_income:
{
  "action": "add_income",
  "description": string,
  "source": string,
  "amount": number
}

------------------------
2. DATE:
- The system will handle the date.
- DO NOT include "date" in the output.

------------------------
3. AMOUNT:
- Must be a number (no currency symbols)

------------------------
4. CATEGORY (lowercase only):
- supermercado
- lanche
- moradia
- lazer
- estudo
- investimento
- saúde
- assinaturas

------------------------
5. SOURCE (lowercase only):
- estágio
- freela
- empresa

------------------------
6. DESCRIPTION:
- Short and clear (e.g. "mc donalds", "uber", "aluguel")

------------------------
7. PAYMENT METHOD (lowercase only):
- dinheiro
- débito
- crédito
- pix
- boleto

- If not mentioned, use: "débito"

------------------------
8. ACTION RULES:

- If the user spends money → "add_expense"
- If the user receives money → "add_income"

------------------------
9. MISSING DATA:

- DO NOT generate or assume a date
- If payment_method is missing → use "débito"
- If category is unclear → use "lazer"
- If source is unclear → use "freela"

------------------------
10. If unsure → prefer correctness over guessing.

------------------------
EXAMPLES:

Input: "Gastei 30 reais com comida hoje"
Output:
{
  "action": "add_expense",
  "description": "comida",
  "category": "lanche",
  "amount": 30,
  "payment_method": "débito"
}

Input: "Paguei 120 de aluguel no crédito"
Output:
{
  "action": "add_expense",
  "description": "aluguel",
  "category": "moradia",
  "amount": 120,
  "payment_method": "crédito"
}

Input: "Recebi 1000 reais hoje de um cliente"
Output:
{
  "action": "add_income",
  "description": "cliente",
  "source": "freela",
  "amount": 1000
}
"""

def interpret_user_input(text: str):
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": text}
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except:
        return {"action": "error", "raw": content}