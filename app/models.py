import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import ConfigDict
from sqlmodel import JSON, Field, SQLModel


class AnalysisSource(str, Enum):
    AI = "ai"
    FALLBACK = "fallback"


class FeedbackBase(SQLModel):
    raw_content: str


class FeedbackInput(FeedbackBase):
    """Schema for incoming requests"""

    raw_content: str = Field(
        ..., min_length=10, max_length=5000, description="Customer feedback text"
    )
    pass


class Feedback(FeedbackBase, table=True):
    """
    Database model for stored feedback.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Classification Fields
    sentiment: str = Field(index=True)  # POSITIVE, NEGATIVE, NEUTRAL
    topics: List[str] = Field(default=[], sa_type=JSON)
    is_urgent: bool = Field(default=False, index=True)
    ai_provider: str  # <--- NEW: Shows exactly which model was used
    department: str
    # Observability & Meta
    source: AnalysisSource
    department: str
    ai_provider: str
    needs_review: bool = Field(default=False)
    confidence_score: float = Field(default=0.0)
    model_config = ConfigDict(from_attributes=True)


class FeedbackResponse(FeedbackBase):
    """Schema for API responses"""

    id: uuid.UUID
    sentiment: str
    topics: List[str]
    is_urgent: bool
    source: AnalysisSource

    model_config = ConfigDict(from_attributes=True)
