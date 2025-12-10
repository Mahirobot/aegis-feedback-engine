import uuid
from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import db_write_lock, engine, get_session
from app.logic import analyze_feedback_hybrid, sanitize_text, trigger_alert
from app.models import (
    Feedback,
    FeedbackInput,
    FeedbackResponse,
    ResolutionRequest,
    TicketStatus,
)
from app.workers import process_csv_worker

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("", response_model=FeedbackResponse)
async def ingest_feedback(
    feedback_in: FeedbackInput,
    background_tasks: BackgroundTasks,
    response: Response,
):
    clean_text = sanitize_text(feedback_in.raw_content)
    text_hash = Feedback.generate_hash(clean_text)

    # 1. Dedup Check (Fast Read)
    with Session(engine) as session:
        existing = session.exec(
            select(Feedback).where(Feedback.content_hash == text_hash)
        ).first()
        if existing:
            response.headers["X-Status"] = "Duplicate"
            return existing

    # 2. Analysis (Slow/Hybrid)
    result = await analyze_feedback_hybrid(clean_text)

    # 3. Write (Thread-Safe)
    try:
        with Session(engine) as session:
            db_obj = Feedback(
                raw_content=feedback_in.raw_content, content_hash=text_hash, **result
            )
            session.add(db_obj)

            def safe_commit():
                with db_write_lock:
                    session.commit()

            await run_in_threadpool(safe_commit)
            session.refresh(db_obj)

            if db_obj.is_urgent:
                background_tasks.add_task(
                    trigger_alert,
                    str(db_obj.id),
                    db_obj.raw_content,
                    db_obj.department,
                    db_obj.sentiment,
                )
            return db_obj

    except IntegrityError:
        with Session(engine) as session:
            response.headers["X-Status"] = "Duplicate"
            return session.exec(
                select(Feedback).where(Feedback.content_hash == text_hash)
            ).first()


@router.get("", response_model=List[FeedbackResponse])
async def list_feedback(
    skip: int = 0, limit: int = 50, session: Session = Depends(get_session)
):
    return session.exec(
        select(Feedback).offset(skip).limit(limit).order_by(Feedback.created_at.desc())
    ).all()


@router.patch("/{feedback_id}/resolve")
async def resolve_ticket(
    feedback_id: uuid.UUID,
    request: ResolutionRequest,
    session: Session = Depends(get_session),
):
    item = session.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, "Not found")

    item.status = TicketStatus.RESOLVED
    item.needs_review = False
    item.resolution_note = request.note
    session.add(item)

    with db_write_lock:
        session.commit()
    return {"ok": True}


@router.post("/batch_csv")
async def upload_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    content = await file.read()
    text_content = content.decode("utf-8", errors="replace")
    background_tasks.add_task(process_csv_worker, text_content)
    return {"message": "Processing started in background."}
