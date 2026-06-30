from config.logging_config import get_logger
from database.repositories.generation_job_repository import GenerationJobRepository
from database.session import SessionLocal
from workflow.state import WorkflowState


logger = get_logger("services.generation_job_progress")


def update_generation_job_progress(
    state: WorkflowState,
    *,
    step: str,
    progress: int,
    message: str,
) -> None:
    job_id = str((state.get("etc") or {}).get("job_id") or "").strip()
    if not job_id:
        return

    session = SessionLocal()
    try:
        GenerationJobRepository(session).update_progress(
            job_id,
            step=step,
            progress=progress,
            message=message,
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to update generation job progress job_id=%s", job_id)
    finally:
        session.close()
