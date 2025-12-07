import asyncio
import json
import logging
from typing import Any, Dict

from groq import AsyncGroq
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import settings

from openai import AsyncOpenAI

logger = logging.getLogger("aegis")


# --- GLOBAL CLIENTS ---
# Initialize once to reuse connections (Best Practice)
groq_client = (
    AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
)
openai_client = (
    AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
)
vader_analyzer = SentimentIntensityAnalyzer()


def analyze_heuristic(text: str) -> Dict[str, Any]:
    """
    Deterministic Fallback: <10ms execution time.
    Uses VADER for sentiment and Regex for topics.
    """
    # 1. Sentiment Analysis (VADER)
    # compound score ranges from -1 (Extremely Negative) to +1 (Extremely Positive)
    scores = vader_analyzer.polarity_scores(text)
    compound = scores["compound"]

    if compound >= 0.05:
        sentiment = "POSITIVE"
    elif compound <= -0.05:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"

    # 2. Keyword Topic Extraction (Regex-like)
    text_lower = text.lower()
    keywords = {
        "Billing": [
            "charge",
            "credit",
            "card",
            "refund",
            "bill",
            "invoice",
            "cost",
            "pricing",
        ],
        "Technical": ["bug", "crash", "error", "fail", "slow", "login", "app", "down"],
        "UX": ["ugly", "confusing", "hard", "color", "button", "nav", "interface"],
        "Security": ["password", "hacked", "breach", "suspicious", "auth", "phishing"],
    }

    # Find all matching topics
    topics = [
        topic
        for topic, words in keywords.items()
        if any(w in text_lower for w in words)
    ]
    if not topics:
        topics.append("General")

    # 3. Urgency Detection
    urgent_keywords = [
        "lawsuit",
        "sue",
        "illegal",
        "gdpr",
        "emergency",
        "fraud",
        "police",
        "danger",
    ]
    is_urgent = any(w in text_lower for w in urgent_keywords)

    # Escalate urgency if sentiment is extremely negative (e.g., "I hate this!")
    if sentiment == "NEGATIVE" and compound < -0.6:
        is_urgent = True

    return {
        "sentiment": sentiment,
        "topics": topics,
        "is_urgent": is_urgent,
        "confidence_score": 0.5,
        "ai_provider": "vader-regex",
    }


async def call_llm(text: str) -> Dict[str, Any]:
    """
    Calls the primary AI provider (Groq) or secondary (OpenAI).
    Handles mocking if no keys are present.
    """
    # Mock Mode (If no keys are set in .env)
    if not groq_client and not openai_client:
        logger.info("No API keys found. Using Mock LLM mode.")
        await asyncio.sleep(0.3)  # Simulate network latency
        result = analyze_heuristic(text)
        result["ai_provider"] = "mock-llm"
        result["confidence_score"] = 0.95
        return result

    system_prompt = (
        "You are a classification engine. Return VALID JSON ONLY. "
        'Schema: {"sentiment": "POSITIVE"|"NEGATIVE"|"NEUTRAL", '
        '"topics": ["Billing", "Technical", "UX", "Security", "General"], '
        '"is_urgent": boolean}'
    )

    try:
        if groq_client:
            response = await groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                model="llama3-8b-8192",
                response_format={"type": "json_object"},
                temperature=0,
                timeout=2.0,
            )
            provider = "groq-llama3"
            content = response.choices[0].message.content

        elif openai_client:
            response = await openai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                temperature=0,
            )
            provider = "openai-gpt4o-mini"
            content = response.choices[0].message.content

        # Robust Parsing
        data = json.loads(content)

        return {
            "sentiment": data.get("sentiment", "NEUTRAL").upper(),
            "topics": data.get("topics", ["General"]),
            "is_urgent": data.get("is_urgent", False),
            "confidence_score": 0.99,
            "ai_provider": provider,
        }

    except Exception as e:
        logger.error(f"LLM Provider Failed: {str(e)}")
        raise e  # Propagate error so the Orchestrator knows to switch to Fallback


async def analyze_feedback_hybrid(text: str) -> Dict[str, Any]:
    """
    Orchestrator: Attempts AI analysis with a hard timeout.
    Falls back to Heuristic engine if AI is slow or down.
    """
    # 1. Always prepare the fallback result first (it's cheap)
    heuristic_result = analyze_heuristic(text)

    try:
        # 2. Race Logic: Try AI, but kill it if it takes too long
        ai_result = await asyncio.wait_for(
            call_llm(text), timeout=settings.AI_TIMEOUT_SECONDS
        )
        return {**ai_result, "source": "ai"}

    except asyncio.TimeoutError:
        logger.warning(
            f"AI Timeout (> {settings.AI_TIMEOUT_SECONDS}s). Using Fallback."
        )
        return {**heuristic_result, "source": "fallback"}

    except Exception as e:
        logger.error(f"AI Exception. Using Fallback. Error: {e}")
        return {**heuristic_result, "source": "fallback"}
