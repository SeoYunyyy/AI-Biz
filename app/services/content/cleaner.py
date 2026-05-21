# app/services/content/cleaner.py

import re


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    return text[:10000]