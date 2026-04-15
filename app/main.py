from fastapi import FastAPI
from app.llm import interpret_user_input
from app.actions import handle_action

app = FastAPI()


@app.post('/test')
def test(payload: dict) -> dict:
    text  = payload.get("message")
    data = interpret_user_input(text)
    result = handle_action(data)
    return {
        "input": text,
        "parsed": data,
        "result": result
    }