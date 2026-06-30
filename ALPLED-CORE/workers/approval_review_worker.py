from __future__ import annotations

import asyncio
import os
import socket
import threading
from contextlib import AbstractContextManager

from fastapi.encoders import jsonable_encoder

from agents.approval_review.agent import ApprovalReviewAgent
from agents.approval_review.repository import ApprovalReviewRepository
from config.logging_config import get_logger
from config.settings import get_settings
from database.repositories.approval_review_job_repository import (
    ApprovalReviewJobRepository,
)
from database.session import SessionLocal


logger = get_logger("workers.approval_review_worker")


class ApprovalReviewHeartbeat(
    AbstractContextManager["ApprovalReviewHeartbeat"]
):
    def __init__(self, job_id: str, interval: float) -> None:
        self.job_id = job_id
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"approval-review-heartbeat-{job_id}",
            daemon=True,
        )

    def __enter__(self) -> "ApprovalReviewHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stop_event.set()
        self._thread.join(timeout=max(self.interval, 1.0) + 1.0)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            session = SessionLocal()
            try:
                ApprovalReviewJobRepository(session).touch_heartbeat(self.job_id)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "Approval review heartbeat failed job_id=%s",
                    self.job_id,
                )
            finally:
                session.close()


class ApprovalReviewWorker:
    def __init__(self, *, worker_id: str | None = None) -> None:
        settings = get_settings()
        self.worker_id = worker_id or (
            f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}:approval-review"
        )
        self.heartbeat_interval = settings.job_worker_heartbeat_interval

    def run_once(self) -> bool:
        session = SessionLocal()
        try:
            job = ApprovalReviewJobRepository(session).claim_next(self.worker_id)
            if job is None:
                session.rollback()
                return False
            session.commit()
            job_id = job.job_id
            docs_aprv_sn = job.docs_aprv_sn
            docs_sn = job.docs_sn
            docs_dtl_sn = job.approval_request_docs_dtl_sn
        except Exception:
            session.rollback()
            logger.exception("Failed to claim approval review job")
            return False
        finally:
            session.close()

        logger.info("Approval review job started job_id=%s", job_id)
        execution_session = SessionLocal()
        try:
            callback = self._progress_callback(job_id)
            snapshot_callback = self._snapshot_callback(job_id)
            with ApprovalReviewHeartbeat(job_id, self.heartbeat_interval):
                result = ApprovalReviewAgent(
                    ApprovalReviewRepository(execution_session),
                    progress_callback=callback,
                    snapshot_callback=snapshot_callback,
                ).execute(docs_sn, docs_dtl_sn, docs_aprv_sn)
            execution_session.rollback()
            self._mark_succeeded(job_id, result)
        except Exception as exc:
            execution_session.rollback()
            logger.exception("Approval review job failed job_id=%s", job_id)
            self._mark_failed(
                job_id,
                "APPROVAL_REVIEW_FAILED",
                str(exc) or "정합성 검증 실행에 실패했습니다.",
            )
        finally:
            execution_session.close()
        return True

    @staticmethod
    def _progress_callback(job_id: str):
        def update(step: str, progress: int, message: str) -> None:
            session = SessionLocal()
            try:
                ApprovalReviewJobRepository(session).update_progress(
                    job_id,
                    step=step,
                    progress=progress,
                    message=message,
                )
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "Failed to update approval review progress job_id=%s",
                    job_id,
                )
            finally:
                session.close()

        return update

    @staticmethod
    def _snapshot_callback(job_id: str):
        def update(
            before_docs_dtl_sn: int,
            after_docs_dtl_sn: int,
            before_data,
            after_data,
        ) -> None:
            session = SessionLocal()
            try:
                ApprovalReviewJobRepository(session).update_snapshots(
                    job_id,
                    before_docs_dtl_sn=before_docs_dtl_sn,
                    after_docs_dtl_sn=after_docs_dtl_sn,
                    before_data=before_data,
                    after_data=after_data,
                )
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "Failed to persist approval review snapshots job_id=%s",
                    job_id,
                )
                raise
            finally:
                session.close()

        return update

    @staticmethod
    def _mark_succeeded(
        job_id: str,
        result: dict,
    ) -> None:
        session = SessionLocal()
        try:
            ApprovalReviewJobRepository(session).mark_succeeded(
                job_id,
                jsonable_encoder(result),
            )
            session.commit()
            logger.info("Approval review job succeeded job_id=%s", job_id)
        except Exception:
            session.rollback()
            logger.exception(
                "Failed to persist approval review success job_id=%s",
                job_id,
            )
        finally:
            session.close()

    @staticmethod
    def _mark_failed(
        job_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        session = SessionLocal()
        try:
            ApprovalReviewJobRepository(session).mark_failed(
                job_id,
                error_code,
                error_message,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "Failed to persist approval review failure job_id=%s",
                job_id,
            )
        finally:
            session.close()


async def run_approval_review_worker_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    worker = ApprovalReviewWorker()
    logger.info("Approval review worker loop started worker_id=%s", worker.worker_id)
    while not stop_event.is_set():
        processed = await asyncio.to_thread(worker.run_once)
        if not processed:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.job_worker_poll_interval,
                )
            except TimeoutError:
                pass
    logger.info("Approval review worker loop stopped worker_id=%s", worker.worker_id)
