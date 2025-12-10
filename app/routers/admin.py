import csv
import io

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import AnalysisSource, Feedback
from app.workers import reconcile_data_worker

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def get_stats(session: Session = Depends(get_session)):
    total = session.exec(select(func.count(Feedback.id))).one()
    urgent = session.exec(
        select(func.count(Feedback.id)).where(Feedback.is_urgent == True)
    ).one()
    fallback = session.exec(
        select(func.count(Feedback.id)).where(
            Feedback.source == AnalysisSource.FALLBACK
        )
    ).one()
    return {"total": total, "urgent": urgent, "fallback": fallback}


@router.post("/reconcile")
async def force_reconciliation(
    background_tasks: BackgroundTasks, session: Session = Depends(get_session)
):
    items = session.exec(
        select(Feedback).where(Feedback.source == AnalysisSource.FALLBACK)
    ).all()
    for item in items:
        background_tasks.add_task(reconcile_data_worker, str(item.id))
    return {"message": f"Queued {len(items)} items."}


@router.get("/reviews")
async def get_review_queue(session: Session = Depends(get_session)):
    return session.exec(select(Feedback).where(Feedback.needs_review == True)).all()


@router.get("/reviews/csv")
async def export_reviews_csv(session: Session = Depends(get_session)):
    results = session.exec(select(Feedback).where(Feedback.needs_review == True)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Sentiment", "Urgent", "Dept", "Source", "Content"])
    for row in results:
        writer.writerow(
            [
                row.id,
                row.sentiment,
                row.is_urgent,
                row.department,
                row.source,
                row.raw_content,
            ]
        )
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=review_queue.csv"},
    )
