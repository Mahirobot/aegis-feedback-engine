import asyncio
import json
import logging
import re
from typing import Any, Dict, List

import httpx
from groq import AsyncGroq, RateLimitError
from openai import AsyncOpenAI
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import settings
from app.models import TOPIC_TO_DEPT_MAP, AIProvider, Department, Sentiment

logger = logging.getLogger("aegis")

# --- SINGLETON CLIENTS ---
# Initialize only if keys exist to save resources
groq_client = (
    AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
)
openai_client = (
    AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
)
vader_analyzer = SentimentIntensityAnalyzer()

# --- CONCURRENCY CONTROL ---
# Limit concurrent AI requests to prevent API rate limiting.
ai_semaphore = asyncio.Semaphore(50)


def sanitize_text(text: str) -> str:
    """
    Input Sanitization.
    1. Removes HTML tags to prevent XSS/Prompt Injection.
    2. Truncates text to 512 chars to bound LLM costs.
    """
    clean_text = re.sub(r"<[^>]*>", "", text)
    return clean_text[:512]


def map_topics_to_department(topics: List[str]) -> str:
    """Matches the first known topic to a Department."""
    for topic in topics:
        if topic in TOPIC_TO_DEPT_MAP:
            return TOPIC_TO_DEPT_MAP[topic]
    return Department.UNASSIGNED


def analyze_heuristic(text: str) -> Dict[str, Any]:
    """
    FAST PATH: <10ms Deterministic Analysis.
    Used when AI is too slow, down, or for initial triage.
    """
    # 1. Sentiment (VADER)
    scores = vader_analyzer.polarity_scores(text)
    compound = scores["compound"]

    if compound >= 0.05:
        sentiment = Sentiment.POSITIVE
    elif compound <= -0.05:
        sentiment = Sentiment.NEGATIVE
    else:
        sentiment = Sentiment.NEUTRAL

    # 2. Topic Extraction (Keyword Regex)
    text_lower = text.lower()
    keywords = {
        "Billing": ["charge", "credit", "card", "refund", "bill", "invoice", "cost"],
        "Technical": [
            "bug",
            "crash",
            "error",
            "fail",
            "slow",
            "login",
            "app",
            "500",
            "404",
        ],
        "UX": ["ugly", "confusing", "hard", "color", "button", "nav", "interface"],
        "Security": ["password", "hacked", "breach", "suspicious", "auth", "phishing"],
    }

    topics = [
        topic
        for topic, words in keywords.items()
        if any(w in text_lower for w in words)
    ]
    if not topics:
        topics.append("General")

    # 3. Urgency Detection
    # Urgent if: Specific danger keywords present OR (Negative Sentiment + High Intensity)
    danger_keywords = [
        "lawsuit",
        "sue",
        "illegal",
        "gdpr",
        "emergency",
        "fraud",
        "police",
    ]
    is_urgent = any(w in text_lower for w in danger_keywords)

    if sentiment == Sentiment.NEGATIVE and compound < -0.6:
        is_urgent = True

    return {
        "sentiment": sentiment,
        "topics": topics,
        "is_urgent": is_urgent,
        "confidence_score": 0.5,
        "ai_provider": AIProvider.VADER,
    }


def validate_llm_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates that the LLM returned strict JSON matching our Enums.
    """
    # 1. Validate Sentiment
    valid_sentiments = {s.value for s in Sentiment}
    sentiment = str(data.get("sentiment", "")).upper()
    if sentiment not in valid_sentiments:
        # Graceful fallback to NEUTRAL if LLM hallucinates a new emotion
        sentiment = Sentiment.NEUTRAL.value

    # 2. Validate Topics
    topics = data.get("topics", [])
    if not isinstance(topics, list) or not topics:
        topics = ["General"]

    return {
        "sentiment": sentiment,
        "topics": topics,
        "is_urgent": bool(data.get("is_urgent", False)),
    }


async def call_llm(text: str) -> Dict[str, Any]:
    """
    SLOW PATH: Calls external AI APIs.
    """
    # Mock Mode Check
    if settings.ENABLE_MOCK_MODE or (not groq_client and not openai_client):
        await asyncio.sleep(0.3)  # Simulate network latency
        result = analyze_heuristic(text)
        result["ai_provider"] = AIProvider.MOCK
        result["confidence_score"] = 0.95
        return result

    system_prompt = (
        "You are a sentiment classification engine. Return VALID JSON ONLY. "
        'Schema: {"sentiment": "POSITIVE"|"NEGATIVE"|"NEUTRAL", '
        '"topics": ["Billing", "Technical", "UX", "Security", "General"], '
        '"is_urgent": boolean}'
    )

    try:
        content = ""
        provider = AIProvider.UNKNOWN

        # Priority 1: Groq (Fastest)
        if groq_client:
            response = await groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                model=settings.AI_MODEL_GROQ,
                response_format={"type": "json_object"},
                temperature=0,
                timeout=5.0,
            )
            provider = AIProvider.GROQ
            content = response.choices[0].message.content

        # Priority 2: OpenAI (Backup)
        elif openai_client:
            response = await openai_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                model=settings.AI_MODEL_OPENAI,
                response_format={"type": "json_object"},
                temperature=0,
            )
            provider = AIProvider.OPENAI
            content = response.choices[0].message.content

        # Parse & Validate
        raw_data = json.loads(content)
        validated = validate_llm_response(raw_data)

        return {
            **validated,
            "confidence_score": 0.99,
            "ai_provider": provider,
        }

    except RateLimitError as e:
        logger.warning(f"Rate Limit: {e}")
        raise e
    except Exception as e:
        logger.error(f"LLM Failed: {e}")
        raise e


async def analyze_feedback_hybrid(clean_text: str) -> Dict[str, Any]:
    """
    THE RACE CONDITION:
    Races the LLM against a 500ms clock.
    Returns Heuristic result if LLM times out.
    """
    # 1. Always run Heuristic (Fast fallback)
    heuristic_result = analyze_heuristic(clean_text)

    # 2. Try AI (Protected by Semaphore)
    async with ai_semaphore:
        try:
            # Race logic
            ai_result = await asyncio.wait_for(
                call_llm(clean_text), timeout=settings.AI_TIMEOUT_SECONDS
            )
            final_result = {**ai_result, "source": "ai"}

        except asyncio.TimeoutError:
            logger.warning(
                f"⚡ AI Timeout (> {settings.AI_TIMEOUT_SECONDS}s). Using VADER."
            )
            final_result = {**heuristic_result, "source": "fallback"}

        except Exception:
            # Any other AI failure triggers fallback
            final_result = {**heuristic_result, "source": "fallback"}

    # 3. Final Polish
    final_result["department"] = map_topics_to_department(
        final_result.get("topics", [])
    )

    return final_result


async def trigger_alert(
    feedback_id: str, content: str, department: str, sentiment: str
):
    """
    Sends alerts for Urgent items.
    """
    message = (
        f"**URGENT FEEDBACK**\n"
        f"**ID:** `{feedback_id}`\n"
        f"**Dept:** {department}\n"
        f"**Sent:** {sentiment}\n"
        f"**Msg:** {content}"
    )

    if settings.DISCORD_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    settings.DISCORD_WEBHOOK_URL, json={"content": message}
                )
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
    else:
        logger.critical(f"MOCK ALERT: {message}")
