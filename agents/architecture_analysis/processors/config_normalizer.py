# 아키텍처 설정을 운영 DB row/ORM/state dict에서 에이전트 내부 표준 스키마로 정규화합니다.

from __future__ import annotations

from typing import Any


CONFIG_COLUMNS = [
    "prj_net_sn",
    "prj_sn",
    "prj_net_nm",
    "prj_net_prps",
    "mid_stack",
    "fwl_settings",
    "auth_method",
    "expected_smtn",
    "cloud_yn",
    "hard_spec",
    "etc_note",
    "reg_dt",
    "reg_user_sn",
    "mod_dt",
    "mod_user_sn",
]


def normalize_architecture_config(value: Any) -> dict[str, Any]:
    """아키텍처 설정을 내부 표준 key로 통일합니다.

    운영에서는 architecture_config가 다음 형태 중 하나로 들어올 수 있습니다.
    - state["etc"]["architecture_config"] dict
    - Repository가 반환한 ORM 객체
    - Repository가 반환한 dict
    - Repository가 반환한 list[dict|ORM]
    - run 파일 테스트용 tuple/list row

    이 함수는 원본 필드를 보존하면서 agent/prompts/processors가 안정적으로 읽는 표준 키를 추가합니다.
    """
    raw = _to_dict(value)
    if not raw:
        return {}

    networks = _normalize_networks(raw)
    primary = networks[0] if networks else raw

    normalized: dict[str, Any] = {
        **raw,
        "raw_architecture_config": raw,
        "networks": networks,
        "network_name": _first(
            primary.get("network_name"),
            primary.get("prj_net_nm"),
            raw.get("network_name"),
            raw.get("prj_net_nm"),
        ),
        "network_purpose": _first(
            primary.get("network_purpose"),
            primary.get("network_description"),
            primary.get("prj_net_prps"),
            raw.get("network_purpose"),
            raw.get("network_description"),
            raw.get("prj_net_prps"),
        ),
        "network_description": _first(
            primary.get("network_description"),
            primary.get("network_purpose"),
            primary.get("prj_net_prps"),
            raw.get("network_description"),
            raw.get("network_purpose"),
            raw.get("prj_net_prps"),
        ),
        "middleware_stack": _first(
            primary.get("middleware_stack"),
            primary.get("mid_stack"),
            raw.get("middleware_stack"),
            raw.get("mid_stack"),
        ),
        "firewall_setting": _first(
            primary.get("firewall_setting"),
            primary.get("fwl_settings"),
            raw.get("firewall_setting"),
            raw.get("fwl_settings"),
        ),
        "auth_method": _first(primary.get("auth_method"), raw.get("auth_method")),
        "expected_user_count": _first(
            primary.get("expected_user_count"),
            primary.get("expected_ccu"),
            primary.get("expected_smtn"),
            raw.get("expected_user_count"),
            raw.get("expected_ccu"),
            raw.get("expected_smtn"),
        ),
        "cloud_yn": _first(primary.get("cloud_yn"), primary.get("is_cloud"), raw.get("cloud_yn"), raw.get("is_cloud")),
        "hardware_spec": _first(
            primary.get("hardware_spec"),
            primary.get("server_hardware_spec"),
            primary.get("hard_spec"),
            raw.get("hardware_spec"),
            raw.get("server_hardware_spec"),
            raw.get("hard_spec"),
        ),
        "description_note": _first(
            primary.get("description_note"),
            primary.get("etc_note"),
            primary.get("description"),
            raw.get("description_note"),
            raw.get("etc_note"),
            raw.get("description"),
        ),
    }

    normalized["is_cloud"] = _cloud_bool(normalized.get("cloud_yn"))
    normalized["architecture_input_text"] = _build_input_text(normalized)
    return normalized


def _normalize_networks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = raw.get("networks") or raw.get("network_configs") or raw.get("architecture_networks")
    if candidate is None:
        return []
    if isinstance(candidate, dict):
        candidate = [candidate]
    if not isinstance(candidate, list):
        return []
    result: list[dict[str, Any]] = []
    for item in candidate:
        normalized = _to_dict(item)
        if normalized:
            result.append(normalized)
    return result


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        # list[dict] 같은 복수 row면 networks로 감싼다.
        if value and all(isinstance(item, (dict, object)) for item in value) and not all(_is_scalar(item) for item in value):
            if all(isinstance(item, dict) or hasattr(item, "__dict__") for item in value):
                return {"networks": [_to_dict(item) for item in value]}
        return {CONFIG_COLUMNS[i]: value[i] for i in range(min(len(value), len(CONFIG_COLUMNS)))}
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {}


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None)))


def _first(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _cloud_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"y", "yes", "true", "1", "cloud", "클라우드"}:
        return True
    if text in {"n", "no", "false", "0", "on-prem", "onprem", "온프레미스", "내부"}:
        return False
    return None


def _build_input_text(config: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in [
        "network_name",
        "network_purpose",
        "network_description",
        "middleware_stack",
        "firewall_setting",
        "auth_method",
        "expected_user_count",
        "cloud_yn",
        "hardware_spec",
        "description_note",
    ]:
        value = config.get(key)
        if value is not None and str(value).strip():
            parts.append(str(value).strip())

    for network in config.get("networks") or []:
        if isinstance(network, dict):
            for key in ["prj_net_nm", "prj_net_prps", "mid_stack", "fwl_settings", "auth_method", "hard_spec", "etc_note"]:
                value = network.get(key)
                if value is not None and str(value).strip():
                    parts.append(str(value).strip())

    # 순서 보존 중복 제거
    deduped: list[str] = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    return " | ".join(deduped)
