# utils/backend.py
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("FINSIGHTS_API_URL", "http://localhost:8000/query")


def query_backend(question: str, session_id: Optional[str] = None) -> str:
    """
    Call your Finsights backend REST API.
    Adjust payload and expected response to your actual backend.
    """
    try:
        payload = {"question": question, "session_id": session_id}
        resp = requests.post(BACKEND_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("answer", "Backend did not return an 'answer' field.")
    except Exception as exc:
        return f"Sorry, the Finsights backend is not reachable right now:\n\n`{exc}`"
