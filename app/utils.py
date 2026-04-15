# Custom util functions

def format_label(text: str) -> str:
    if not text:
        return text

    words = text.split()
    return " ".join([w.capitalize() for w in words])