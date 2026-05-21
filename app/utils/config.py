# app/utils/config.py

from dotenv import load_dotenv
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

OPENAI_SUMMARY_MODEL = "gpt-4.1-mini"
OPENAI_TAG_MODEL = "gpt-4.1-mini"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"