from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import Any


_REQUEST_ID_CONTEXT: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> Token[str]:
    return _REQUEST_ID_CONTEXT.set(request_id or "-")


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID_CONTEXT.reset(token)


def get_request_id() -> str:
    return _REQUEST_ID_CONTEXT.get()


def get_request_id_from_state(state: Mapping[str, Any] | None) -> str | None:
    if state is None:
        return None
    etc = state.get("etc")
    if not isinstance(etc, Mapping):
        return None
    request_id = etc.get("request_id")
    if request_id in (None, ""):
        return None
    return str(request_id)


def bind_log_extra(
    phase: str,
    *,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "request_id": request_id or get_request_id(),
        **fields,
    }


def bind_state_log_extra(
    state: Mapping[str, Any] | None,
    phase: str,
    **fields: Any,
) -> dict[str, Any]:
    return bind_log_extra(
        phase,
        request_id=get_request_id_from_state(state),
        **fields,
    )
