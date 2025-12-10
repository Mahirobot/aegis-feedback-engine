# tests/test_api.py
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import func, select

from app.models import Feedback

# --- TEST SUITE ---


@pytest.mark.asyncio
async def test_deduplication_race_condition(client, session):
    """
    SCENARIO: Spam Attack / Race Condition.

    Test:
        Simulate a burst of 20 identical requests arriving simultaneously.

    Expected Behavior:
        - The API should accept all requests (status 200 or 201).
        - The Logic layer should identify the duplicates.
        - The Database should contain ONLY 1 record (Idempotency).
        - 19 responses should indicate they were deduplicated (X-Status header).
    """
    # 1. Prepare payload
    payload = {"raw_content": "This is a race condition test."}

    # 2. Fire 20 requests concurrently using asyncio.gather
    tasks = [client.post("/feedback", json=payload) for _ in range(20)]
    responses = await asyncio.gather(*tasks)

    # 3. Analyze responses
    duplicate_header_count = 0
    for res in responses:
        # 200 = OK (Duplicate returned), 201 = Created (New Item)
        assert res.status_code in [200, 201]
        if res.headers.get("X-Status") == "Duplicate":
            duplicate_header_count += 1

    # 4. Verify Database Integrity
    # There should be exactly one record, despite 20 writes attempted.
    total_in_db = session.exec(select(func.count(Feedback.id))).one()

    assert (
        total_in_db == 1
    ), "Database should verify content hash and store only unique item"
    assert (
        duplicate_header_count >= 19
    ), "At least 19 requests should be flagged as duplicates"


@pytest.mark.asyncio
async def test_sqlite_concurrency_lock(client, session):
    """
    SCENARIO: High Traffic Volume (Unique Content).

    Test:
        Fire 50 unique requests simultaneously.

    Expected Behavior:
        - SQLite usually fails with 'database is locked' on concurrent writes.
        - Our 'db_write_lock' in main.py should serialize these writes.
        - All 50 requests should succeed, and 50 records should exist in DB.
    """
    # 1. Generate 50 unique payloads
    payloads = [
        {"raw_content": f"Unique Load Test Item {uuid.uuid4()}"} for _ in range(50)
    ]

    # 2. Fire requests
    tasks = [client.post("/feedback", json=p) for p in payloads]
    responses = await asyncio.gather(*tasks)

    # 3. Assertions
    for res in responses:
        assert res.status_code in [200, 201], f"Failed request: {res.text}"

    total_in_db = session.exec(select(func.count(Feedback.id))).one()
    assert total_in_db == 50, "All 50 unique items should be persisted"


@pytest.mark.asyncio
async def test_ai_timeout_fallback_logic(client):
    """
    SCENARIO: AI Provider Failure (Latency/Timeout).

    Test:
        Mock the 'call_llm' function to raise an asyncio.TimeoutError.

    Expected Behavior:
        - The API should NOT crash (500 error).
        - The API should catch the timeout.
        - The API should fall back to Heuristic analysis (VADER).
        - Response source should be marked 'fallback'.
    """
    # 1. Mock the AI function to simulate a timeout
    with patch(
        "app.logic.call_llm", side_effect=AsyncMock(side_effect=asyncio.TimeoutError)
    ):

        # 2. Send urgent-sounding payload
        payload = {"raw_content": "The system is down! Lawsuit incoming!"}
        response = await client.post("/feedback", json=payload)

        # 3. Verify Response
        assert response.status_code in [200, 201]
        data = response.json()

        # 4. Verify Fallback Mechanics
        assert (
            data["source"] == "fallback"
        ), "Source should degrade to 'fallback' on timeout"
        assert (
            data["ai_provider"] == "vader-regex"
        ), "Provider should be the heuristic engine"
        assert (
            data["is_urgent"] is True
        ), "Heuristic engine should still detect urgency correctly"
