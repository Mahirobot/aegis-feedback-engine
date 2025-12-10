import asyncio
import csv
import io
import logging
import uuid

from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select

from app.database import db_write_lock, engine
from app.logic import (
    analyze_feedback_hybrid,
    call_llm,
    map_topics_to_department,
    sanitize_text,
)
from app.models import AnalysisSource, Feedback

logger = logging.getLogger("aegis")


async def reconcile_data_worker(feedback_id: str):
    """
    Worker: Re-analyzes 'fallback' data using the LLM when time permits.
    Upgrades data quality from 'Heuristic' to 'AI'.
    """
    try:
        real_uuid = uuid.UUID(feedback_id)
    except ValueError:
        return

    # 1. READ (Snapshot)
    feedback_snapshot = None
    with Session(engine) as session:
        feedback = session.get(Feedback, real_uuid)
        if feedback and feedback.source == AnalysisSource.FALLBACK:
            feedback_snapshot = {
                "raw_content": feedback.raw_content,
                "was_urgent": feedback.is_urgent,
            }

    if not feedback_snapshot:
        return

    # 2. PROCESS (Slow AI)
    try:
        clean_text = sanitize_text(feedback_snapshot["raw_content"])
        ai_result = await call_llm(clean_text)
    except Exception as e:
        logger.error(f"Reconcile failed for {feedback_id}: {e}")
        return

    # 3. WRITE (Thread-safe)
    with Session(engine) as session:
        feedback = session.get(Feedback, real_uuid)
        if not feedback:
            return

        missed_urgency = ai_result["is_urgent"] and not feedback_snapshot["was_urgent"]

        feedback.sentiment = ai_result["sentiment"]
        feedback.topics = ai_result["topics"]
        feedback.is_urgent = ai_result["is_urgent"]
        feedback.source = AnalysisSource.AI
        feedback.ai_provider = ai_result["ai_provider"]
        feedback.department = map_topics_to_department(ai_result["topics"])

        if missed_urgency:
            feedback.needs_review = True
            logger.info(f"Reconcile found missed urgency in {feedback_id}")

        session.add(feedback)

        with db_write_lock:
            session.commit()


async def process_csv_worker(csv_content: str):
    """Worker: Processes bulk CSV uploads with rate limiting."""
    with Session(engine) as session:
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        count = 0

        for row in csv_reader:
            text = row.get("text") or row.get("raw_content")
            if not text:
                continue

            clean_text = sanitize_text(text)
            text_hash = Feedback.generate_hash(clean_text)

            # Dedup check
            existing = session.exec(
                select(Feedback).where(Feedback.content_hash == text_hash)
            ).first()
            if existing:
                continue

            result = await analyze_feedback_hybrid(text)

            db_obj = Feedback(raw_content=text, content_hash=text_hash, **result)
            session.add(db_obj)
            count += 1

            # Batch Commit (Every 10)
            if count % 10 == 0:
                with db_write_lock:
                    session.commit()
                await asyncio.sleep(0.01)  # Yield to event loop

        with db_write_lock:
            session.commit()
        logger.info(f"CSV Batch Complete: {count} records.")


async def run_periodic_reconciliation():
    """Scheduler loop."""
    while True:
        try:
            await asyncio.sleep(5)
            with Session(engine) as session:
                statement = (
                    select(Feedback)
                    .where(Feedback.source == AnalysisSource.FALLBACK)
                    .limit(10)
                )
                items = session.exec(statement).all()

                for item in items:
                    await reconcile_data_worker(str(item.id))
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Scheduler Error: {e}")
            await asyncio.sleep(5)
