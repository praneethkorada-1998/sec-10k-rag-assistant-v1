import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "SEC 10-K RAG Demo contact@example.com"
)

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "text-embedding-3-small"
)

CHAT_MODEL = os.getenv(
    "CHAT_MODEL",
    "gpt-4.1-mini"
)