import os
import httpx
from fastapi import FastAPI, Request

from app.llm import interpret_user_input
from app.actions import handle_action
from app.utils import format_message

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

@app.post('/test')
def test(payload: dict) -> dict:
    """Endpoint for testing via curl"""
    text  = payload.get("message")
    data = interpret_user_input(text)
    result = handle_action(data)
    return {
        "input": text,
        "parsed": data,
        "result": result
    }

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text")

    if not text or not chat_id:
        return {"ok": True}
    
    parsed = interpret_user_input(text)
    result = handle_action(parsed)
    
    response = format_message(
        action = result.get("action"), 
        amount = result.get("amount"), 
        category = result.get("category")
    )
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": response
                }
            )
    except Exception as e:
        print(f"Error: {e}")

    return {"ok": True}