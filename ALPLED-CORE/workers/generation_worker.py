from __future__ import annotations

import asyncio
import os
import socket
import threading
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder

from config.logging_config import configure_logging, get_logger
from config.settings import get_settings
from database.repositories.generation_job_repository import GenerationJobRepository
from database.session import SessionLocal
from workflow.graph import workflow


logger = get_logger("workers.generation_worker")


class JobHeartbeat(AbstractContextManager["JobHeartbeat"]):
    def __init__(self, job_id: str, interval: float) -> None:
        self.job_id = job_id
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"job-heartbeat-{job_id}",
            daemon=True,
        )

    def __enter__(self) -> "JobHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stop_event.set()
        self._thread.join(timeout=max(self.interval, 1.0) + 1.0)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            session = SessionLocal()
            try:
                GenerationJobRepository(session).touch_heartbeat(self.job_id)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Generation job heartbeat failed job_id=%s", self.job_id)
            finally:
                session.close()


class GenerationWorker:
    def __init__(
        self,
        *,
        worker_id: str | None = None,
        heartbeat_interval: float | None = None,
    ) -> None:
        settings = get_settings()
        self.worker_id = worker_id or (
            f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"
        )
        self.heartbeat_interval = (
            heartbeat_interval or settings.job_worker_heartbeat_interval
        )
        self.stale_timeout = settings.job_worker_stale_timeout

    def run_once(self) -> bool:
        session = SessionLocal()
        try:
            repository = GenerationJobRepository(session)
            requeued, failed = repository.recover_stale_jobs(
                datetime.now() - timedelta(seconds=self.stale_timeout)
            )
            if requeued or failed:
                logger.warning(
                    "Recovered stale generation jobs requeued=%s failed=%s",
                    requeued,
                    failed,
                )
            job = repository.claim_next()
            if job is None:
                session.commit()
                return False
            session.commit()
            job_id = job.job_id
            request_payload = dict(job.request_json)
            request_id = job.request_id
        except Exception:
            session.rollback()
            logger.exception("Failed to claim generation job")
            return False
        finally:
            session.close()

        state = request_payload
        state.setdefault("etc", {})
        state["etc"]["job_id"] = job_id
        state["etc"]["request_id"] = request_id

        logger.info("Generation job started job_id=%s worker_id=%s", job_id, self.worker_id)
        try:
            with JobHeartbeat(job_id, self.heartbeat_interval):
                result_state = workflow.invoke(state)
            self._finish_job(job_id, result_state)
        except Exception as exc:
            logger.exception("Generation job raised an exception job_id=%s", job_id)
            self._mark_failed(
                job_id,
                error_code="GENERATION_WORKER_FAILED",
                error_message=str(exc) or "산출물 생성 Worker 실행에 실패했습니다.",
            )
        return True

    def _finish_job(self, job_id: str, result_state: dict[str, Any]) -> None:
        response_result = {
            "next_action": result_state.get("next_action"),
            "final_document_json": result_state.get("final_document_json"),
            "export_result": result_state.get("export_result"),
            "validation_result": result_state.get("validation_result"),
            "cleanup_result": result_state.get("cleanup_result"),
            "warnings": result_state.get("warnings", []),
            "errors": result_state.get("errors", []),
        }
        if (result_state.get("etc") or {}).get("debug"):
            response_result["agent_outputs"] = result_state.get("agent_outputs", {})
            response_result["repair_history"] = result_state.get("repair_history", [])

        if result_state.get("status") == "DONE":
            export_result = result_state.get("export_result")
            docs_sn = (
                export_result.get("docs_sn")
                if isinstance(export_result, dict) and isinstance(export_result.get("docs_sn"), int)
                else None
            )
            session = SessionLocal()
            try:
                GenerationJobRepository(session).mark_succeeded(
                    job_id,
                    jsonable_encoder(response_result),
                    docs_sn=docs_sn,
                )
                session.commit()
                logger.info("Generation job succeeded job_id=%s", job_id)
            except Exception:
                session.rollback()
                logger.exception("Failed to persist generation job success job_id=%s", job_id)
            finally:
                session.close()
            return

        errors = result_state.get("errors") or []
        first_error = errors[0] if errors and isinstance(errors[0], dict) else {}
        self._mark_failed(
            job_id,
            error_code=str(first_error.get("code") or "GENERATION_FAILED"),
            error_message=str(
                first_error.get("message") or "산출물 생성 워크플로우가 실패했습니다."
            ),
            result=response_result,
        )

    def _mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        session = SessionLocal()
        try:
            GenerationJobRepository(session).mark_failed(
                job_id,
                error_code=error_code,
                error_message=error_message,
                result=jsonable_encoder(result) if result is not None else None,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to persist generation job failure job_id=%s", job_id)
        finally:
            session.close()


async def run_generation_worker_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    worker = GenerationWorker()
    logger.info("Generation worker loop started worker_id=%s", worker.worker_id)
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
    logger.info("Generation worker loop stopped worker_id=%s", worker.worker_id)


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings)
    if settings.job_auto_create_table:
        from database.engine import engine
        from database.models.generation_job import GenerationJob

        GenerationJob.__table__.create(bind=engine, checkfirst=True)
    stop_event = asyncio.Event()
    try:
        await run_generation_worker_loop(stop_event)
    except KeyboardInterrupt:
        stop_event.set()


if __name__ == "__main__":
    asyncio.run(_main())
