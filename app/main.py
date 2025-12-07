import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.logging import setup_logging
from app.logic import analyze_feedback_hybrid, call_llm
from app.models import AnalysisSource, Feedback, FeedbackInput, FeedbackResponse

logger = setup_logging()
# Database Setup
# check_same_thread=False is needed for SQLite when using background tasks
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})


def get_session():
    with Session(engine) as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create Tables
    SQLModel.metadata.create_all(engine)
    yield
    # Shutdown logic (if any) goes here


app = FastAPI(
    title=settings.APP_TITLE,
    lifespan=lifespan,
    description="Hybrid Sync/Async Feedback Analysis Engine",
)

# --- BACKGROUND WORKER ---
async def reconcile_data_worker(feedback_id: str):
    """
    Background Worker:
    1. Fetches feedback that used fallback.
    2. Retries AI analysis (slow path).
    3. Updates DB and flags human review if drift detected.
    """
    # Wait briefly to avoid race conditions with the initial write
    await asyncio.sleep(1.0)

    # CRITICAL: Open a NEW session for the background task
    with Session(engine) as session:
        feedback = session.get(Feedback, feedback_id)

        if not feedback or feedback.source == AnalysisSource.AI:
            return

        try:
            # Retry AI without timeout constraints
            ai_result = await call_llm(feedback.raw_content)

            # Drift Detection
            sentiment_mismatch = feedback.sentiment != ai_result["sentiment"]
            topic_mismatch = set(feedback.topics) != set(ai_result["topics"])

            # Critical Drift: AI flagged urgent, but fallback didn't
            missed_urgency = ai_result["is_urgent"] and not feedback.is_urgent

            # Update Record
            feedback.sentiment = ai_result["sentiment"]
            feedback.topics = ai_result["topics"]
            feedback.is_urgent = ai_result["is_urgent"]
            feedback.source = AnalysisSource.AI
            feedback.ai_provider = ai_result["ai_provider"]

            # Flag for Human Review if significant disagreement
            if missed_urgency or (sentiment_mismatch and ai_result["is_urgent"]):
                feedback.needs_review = True

            session.add(feedback)
            session.commit()
            print(
                f"Reconciled Feedback {feedback_id}. Missed Urgency: {missed_urgency}"
            )

        except Exception as e:
            print(f"Reconciliation failed for {feedback_id}: {e}")


# --- ENDPOINT ---
@app.post("/feedback", response_model=FeedbackResponse, status_code=200)
async def ingest_feedback(
    feedback_in: FeedbackInput,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Ingests feedback with a <500ms latency guarantee.
    Uses 'Optimistic AI' pattern with 'Heuristic Fallback'.
    """
    # 1. Analyze (Hybrid Strategy)
    result = await analyze_feedback_hybrid(feedback_in.raw_content)

    # 2. Persist
    db_obj = Feedback(raw_content=feedback_in.raw_content, **result)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    # 3. Self-Correction (If needed)
    if db_obj.source == AnalysisSource.FALLBACK:
        background_tasks.add_task(reconcile_data_worker, str(db_obj.id))

    return db_obj
