# app/services/ai/client.py

from openai import AsyncOpenAI
from app.utils.config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)