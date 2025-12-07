import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_heuristic_fallback_on_timeout():
    """
    Simulates a slow AI (2.0s delay) to ensure the API
    returns a Fallback response instantly (<0.5s logic timeout).
    """
    # Force call_llm to hang
    with patch(
        "app.logic.call_llm", side_effect=AsyncMock(side_effect=asyncio.TimeoutError)
    ):

        payload = {"raw_content": "This billing issue is a nightmare! I will sue!"}
        response = client.post("/feedback", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Assertions
        assert data["source"] == "fallback"
        assert data["is_urgent"] is True  # Regex should catch 'sue'
        assert "Billing" in data["topics"]  # Regex should catch 'billing'


def test_happy_path_mock():
    """
    Tests the happy path without any keys (Mock Mode).
    """
    # Ensure no keys are present (or mock the env)
    with patch("app.logic.groq_client", None), patch("app.logic.openai_client", None):
        payload = {"raw_content": "The app is great, love the UI."}
        response = client.post("/feedback", json=payload)

        assert response.status_code == 200
        data = response.json()

        assert (
            data["source"] == "fallback"
        )  # Because mock calls heuristic internally in this setup
        assert data["sentiment"] == "POSITIVE"
