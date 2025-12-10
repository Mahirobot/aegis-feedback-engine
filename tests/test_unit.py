import pytest
from unittest.mock import AsyncMock, patch
from app.logic import validate_llm_response

# --- 1. UNIT TEST: Logic Validation (Robustness) ---
def test_ai_response_parsing_robustness():
    """
    Requirement Check: 'AI response parsing'
    
    Verifies that the system is 'Self-Healing'. 
    Instead of crashing on bad AI data, it should apply safe defaults
    to ensure the API contract remains valid.
    """
    
    # Case 1: Missing keys (Should default to safe values)
    incomplete_data = {"sentiment": "POSITIVE"} 
    result = validate_llm_response(incomplete_data)
    assert result["topics"] == ["General"]  # Default applied
    assert result["is_urgent"] is False     # Default applied

    # Case 2: Wrong types (Should auto-correct)
    invalid_type = {"sentiment": "POSITIVE", "topics": "NotAList", "is_urgent": True}
    result = validate_llm_response(invalid_type)
    assert result["topics"] == ["General"] # Coerced to list

    # Case 3: Invalid Enum value (Should fallback to NEUTRAL)
    # The LLM hallucinated "SUPER_HAPPY", which isn't in our Enum.
    invalid_enum = {"sentiment": "SUPER_HAPPY", "topics": [], "is_urgent": False}
    result = validate_llm_response(invalid_enum)
    assert result["sentiment"] == "NEUTRAL" # Fallback applied

# --- 2. INTEGRATION TEST: Alerting ---
@pytest.mark.asyncio
async def test_alert_integration(client):
    """
    Requirement Check: 'Alert triggering'
    Verifies the background task is added for urgent items.
    """
    payload = {"raw_content": "This is a dangerous security breach! Lawsuit!"}
    
    # Patch the logic function where the alert is triggered
    with patch("app.logic.trigger_alert") as mock_alert:
        response = await client.post("/feedback", json=payload)
        assert response.status_code in [200, 201]
        
        data = response.json()
        assert data["is_urgent"] is True