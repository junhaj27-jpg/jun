from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.download_router import router as download_router
from api.generation_router import router as generation_router
from api.health_router import router as health_router
from api.approval_review_router import router as approval_review_router
from config.logging_config import configure_logging, get_logger
from config.logging_context import bind_log_extra, reset_request_id, set_request_id
from config.settings import get_settings


logger = get_logger("main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "Application configured LLM base_url=%s model=%s",
        settings.llm_base_url,
        settings.llm_model_name,
        extra=bind_log_extra("application_configured"),
    )
    yield


app = FastAPI(title="ALPLED Core", lifespan=lifespan)
app.include_router(health_router)
app.include_router(generation_router)
app.include_router(download_router)
app.include_router(approval_review_router)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    token = set_request_id(request_id)
    logger.info(
        "HTTP request started %s %s",
        request.method,
        request.url.path,
        extra=bind_log_extra("http_request_start"),
    )
    try:
        response = await call_next(request)
    except Exception:
        logger.info(
            "HTTP request completed status=500",
            extra=bind_log_extra("http_request_complete"),
        )
        raise
    else:
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed status=%s",
            response.status_code,
            extra=bind_log_extra("http_request_complete"),
        )
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "-")
    logger.warning(
        "HTTP request validation failed",
        extra=bind_log_extra("http_request_validation_failed", request_id=request_id),
    )
    response = await request_validation_exception_handler(request, exc)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    logger.exception(
        "HTTP request raised an unhandled exception",
        extra=bind_log_extra("http_request_unhandled_exception", request_id=request_id),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers={"X-Request-ID": request_id},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
