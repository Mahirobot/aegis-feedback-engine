import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from sqlmodel import JSON, AutoString, Field, SQLModel

# --- ENUMS ---
# Using string-based Enums for easy serialization to JSON/DB


class AnalysisSource(str, Enum):
    AI = "ai"
    FALLBACK = "fallback"


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class AIProvider(str, Enum):
    GROQ = "groq-llama3"
    OPENAI = "openai-gpt4o-mini"
    VADER = "vader-regex"
    MOCK = "mock-llm"
    UNKNOWN = "unknown"


class Department(str, Enum):
    """Routing destinations for feedback."""

    FINANCE = "Customer Success - Finance"
    ENGINEERING = "Engineering - Core"
    PRODUCT = "Product - Design"
    INFOSEC = "InfoSec - Priority"
    SUPPORT = "Customer Support - Triage"
    UNASSIGNED = "Unassigned"


class TicketStatus(str, Enum):
    OPEN = "Open"
    RESOLVED = "Resolved"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


# --- MAPPINGS ---
# Centralized routing logic. Easy to update or move to DB later.
TOPIC_TO_DEPT_MAP: Dict[str, Department] = {
    "Billing": Department.FINANCE,
    "Technical": Department.ENGINEERING,
    "UX": Department.PRODUCT,
    "Security": Department.INFOSEC,
    "General": Department.SUPPORT,
}

# --- DOMAIN MODELS ---


class FeedbackBase(SQLModel):
    """Shared properties for Feedback models."""

    raw_content: str


class FeedbackInput(FeedbackBase):
    """
    Schema for incoming API requests.
    Validates length to prevent DB spam/DoS.
    """

    raw_content: str = Field(
        ...,
        min_length=3,
        max_length=5000,
        description="The raw customer feedback text.",
    )


class ResolutionRequest(BaseModel):
    """Schema for marking a ticket as resolved."""

    note: Optional[str] = None


class Feedback(FeedbackBase, table=True):
    """
    Database Table: 'feedback'
    Stores all analyzed feedback, routing info, and status.
    """

    # Identification
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Core Analysis
    sentiment: Sentiment = Field(index=True, sa_type=AutoString)
    topics: List[str] = Field(default=[], sa_type=JSON)
    is_urgent: bool = Field(default=False, index=True)
    confidence_score: float = Field(default=0.0)

    # Workflow Status
    status: TicketStatus = Field(default=TicketStatus.OPEN, sa_type=AutoString)
    priority: Priority = Field(default=Priority.MEDIUM, sa_type=AutoString)
    resolution_note: Optional[str] = Field(default=None, sa_type=AutoString)
    needs_review: bool = Field(
        default=False, description="Flag for AI vs Human mismatch"
    )

    # Routing & Meta
    department: Department = Field(default=Department.UNASSIGNED, sa_type=AutoString)
    ai_provider: AIProvider = Field(default=AIProvider.UNKNOWN, sa_type=AutoString)
    source: AnalysisSource = Field(sa_type=AutoString, description="AI or Fallback")

    # Deduplication
    # 'content_hash' is indexed and unique to enforce Idempotency at DB level.
    content_hash: str = Field(index=True, unique=True)

    # Configuration for Pydantic V2 to read from ORM objects
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @staticmethod
    def generate_hash(text: str) -> str:
        """Generates SHA-256 hash for deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FeedbackResponse(FeedbackBase):
    """
    Schema for API Responses.
    Hides internal DB fields if necessary (currently exposes most).
    """

    id: uuid.UUID
    sentiment: Sentiment
    topics: List[str]
    is_urgent: bool
    source: AnalysisSource
    ai_provider: AIProvider
    department: Department
    status: TicketStatus
    resolution_note: Optional[str]

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
