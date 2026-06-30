"""비기능 요구사항 Vector 저장 진입점입니다."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid

from config.settings import Settings, get_settings
from tools.vector.embedding_client import embed_text
from tools.result import ToolResult, success_result
from tools.result import error_result


def write_non_functional_requirements(
    requirements: list[dict[str, Any]],
    *,
    project_sn: int | None = None,
    source_path: str | None = None,
    writer: Any | None = None,
    qdrant_client: Any | None = None,
    embedder: Any | None = None,
    collection: str | None = None,
    settings: Settings | None = None,
) -> ToolResult:
    """비기능/제약 요구사항을 Vector DB에 저장합니다.

    writer를 주입하면 테스트용 writer로 위임하고, 기본 실행에서는
    SentenceTransformer 임베딩을 생성해 Qdrant에 upsert합니다.
    """

    targets = [
        item
        for item in requirements
        if isinstance(item, dict) and not _is_functional_requirement(item)
    ]
    if writer is not None:
        writer(targets, project_sn=project_sn, source_path=source_path)
        return success_result({"stored_count": len(targets)})

    if not targets:
        return success_result({"stored_count": 0, "skipped_count": 0, "point_ids": []})

    settings = settings or get_settings()
    selected_collection = collection or settings.alpled_reference_collection
    points = []
    skipped: list[dict[str, Any]] = []

    try:
        for item in targets:
            embedded_text = _embedded_text(item)
            embedding = embed_text(embedded_text, embedder=embedder, settings=settings)
            if not embedding["success"]:
                skipped.append(
                    {
                        "requirement_id": _requirement_id(item),
                        "reason": embedding["error"]["message"],
                    }
                )
                continue
            payload = _payload(item, project_sn=project_sn, source_path=source_path, embedded_text=embedded_text)
            points.append(
                {
                    "id": _point_id(project_sn, source_path, item),
                    "vector": embedding["data"]["embedding"],
                    "payload": payload,
                }
            )

        if not points:
            return error_result(
                "EMBEDDING_WRITE_NO_POINTS",
                "저장 가능한 비기능 요구사항 embedding이 없습니다.",
                {"skipped": skipped},
            )

        qdrant = qdrant_client or _create_qdrant_client(settings)
        _ensure_collection(qdrant, selected_collection, len(points[0]["vector"]))
        _upsert_points(qdrant, selected_collection, points)
        return success_result(
            {
                "stored_count": len(points),
                "skipped_count": len(skipped),
                "point_ids": [point["id"] for point in points],
                "collection": selected_collection,
                "skipped": skipped,
            }
        )
    except ImportError as exc:
        return error_result("EMBEDDING_WRITE_CLIENT_UNAVAILABLE", str(exc))
    except Exception as exc:
        return error_result(
            "EMBEDDING_WRITE_FAILED",
            str(exc),
            {"collection": selected_collection, "stored_candidate_count": len(points)},
        )


def _is_functional_requirement(item: dict[str, Any]) -> bool:
    requirement_type = str(item.get("requirement_type") or item.get("type") or "").strip().lower()
    return requirement_type.startswith("기능") or requirement_type.startswith("functional") or requirement_type == "function"


def _create_qdrant_client(settings: Settings) -> Any:
    from qdrant_client import QdrantClient

    kwargs = {"url": settings.resolved_qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


def _ensure_collection(client: Any, collection_name: str, vector_size: int) -> None:
    if _collection_exists(client, collection_name):
        return
    try:
        from qdrant_client.models import Distance, VectorParams

        vectors_config = VectorParams(size=vector_size, distance=Distance.COSINE)
    except ImportError:
        vectors_config = {"size": vector_size, "distance": "Cosine"}

    client.create_collection(
        collection_name=collection_name,
        vectors_config=vectors_config,
    )


def _collection_exists(client: Any, collection_name: str) -> bool:
    if hasattr(client, "collection_exists"):
        return bool(client.collection_exists(collection_name=collection_name))
    try:
        client.get_collection(collection_name=collection_name)
        return True
    except Exception:
        return False


def _upsert_points(client: Any, collection_name: str, points: list[dict[str, Any]]) -> None:
    try:
        from qdrant_client.models import PointStruct
    except ImportError:
        PointStruct = SimpleNamespace

    client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=point["id"],
                vector=point["vector"],
                payload=point["payload"],
            )
            for point in points
        ],
    )


def _payload(
    item: dict[str, Any],
    *,
    project_sn: int | None,
    source_path: str | None,
    embedded_text: str,
) -> dict[str, Any]:
    requirement_id = _requirement_id(item)
    requirement_type = _normalized_requirement_type(item)
    source_refs = _source_refs(item)
    file_name = Path(source_path).name if source_path else ""
    return {
        "project_sn": project_sn,
        "text": embedded_text,
        "chunk_id": f"project_requirement_{_point_id(project_sn, source_path, item)}",
        "doc_type": "project_non_functional_requirement",
        "domain": "requirements",
        "rfp_id": item.get("rfp_id") or item.get("document_id") or file_name,
        "requirement_id": requirement_id,
        "requirement_source_id": list(dict.fromkeys([requirement_id, *source_refs])),
        "requirement_type": requirement_type,
        "raw_requirement_type": item.get("requirement_type") or item.get("type"),
        "requirement_name": _requirement_name(item),
        "category": _category(item, requirement_type),
        "keywords": _keywords(item),
        "source_type": item.get("source_type") or "RFP",
        "source_name": Path(source_path).stem if source_path else str(item.get("source_name") or ""),
        "source_path": source_path or item.get("source_path") or "",
        "source_file": file_name or str(item.get("source_file") or ""),
        "section": "project non-functional requirements",
        "title": _requirement_name(item) or requirement_id,
        "applies_to": "requirements_definition,erd,db_design,architecture_design,interface_design,test_scenario",
        "priority": item.get("priority") or "project",
        "chunk_type": "project_requirement_source",
        "is_active": True,
        "language": "ko",
        "page": item.get("page") or item.get("page_number"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "content": embedded_text,
        "original_text": _original_text(item),
        "embedded_text": embedded_text,
    }


def _embedded_text(item: dict[str, Any]) -> str:
    parts = [
        f"[{_requirement_id(item)}] {_requirement_name(item)}",
        f"유형: {_normalized_requirement_type(item)}",
        _original_text(item),
        _join(item.get("constraints")),
        _join(item.get("validation_criteria")),
    ]
    return "\n".join(part for part in parts if part)


def _original_text(item: dict[str, Any]) -> str:
    return str(
        item.get("requirement_detail")
        or item.get("detail_text")
        or item.get("description")
        or item.get("requirement_definition")
        or item.get("content")
        or item.get("requirement_text")
        or ""
    ).strip()


def _requirement_id(item: dict[str, Any]) -> str:
    return str(item.get("req_id") or item.get("requirement_id") or item.get("id") or "")


def _requirement_name(item: dict[str, Any]) -> str:
    return str(item.get("req_name") or item.get("requirement_name") or item.get("name") or "").strip()


def _normalized_requirement_type(item: dict[str, Any]) -> str:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("requirement_type"),
            item.get("type"),
            item.get("req_id"),
            _requirement_name(item),
            _original_text(item),
            _join(item.get("constraints")),
        )
    ).lower()
    mapping = [
        ("보안", ("보안", "security", "sec")),
        ("성능", ("성능", "performance", "perf")),
        ("품질", ("품질", "quality")),
        ("인터페이스", ("인터페이스", "interface", "ui", "화면")),
        ("데이터", ("데이터", "개인정보", "이력", "보관", "db", "database")),
        ("운영", ("운영", "operation", "모니터링", "로그", "백업")),
        ("연계", ("연계", "api", "외부", "interface")),
        ("인프라", ("인프라", "서버", "배포", "network", "infra")),
    ]
    for normalized, keywords in mapping:
        if any(keyword.lower() in text for keyword in keywords):
            return normalized
    raw = str(item.get("requirement_type") or item.get("type") or "비기능").strip()
    return raw.replace(" 요구사항", "") or "비기능"


def _category(item: dict[str, Any], requirement_type: str) -> str:
    raw = str(item.get("category") or "").strip()
    if raw:
        return raw
    return {
        "보안": "security_requirement",
        "성능": "performance_requirement",
        "품질": "quality_requirement",
        "인터페이스": "interface_requirement",
        "데이터": "data_requirement",
        "운영": "operation_requirement",
        "연계": "integration_requirement",
        "인프라": "infra_requirement",
    }.get(requirement_type, "non_functional_requirement")


def _keywords(item: dict[str, Any]) -> list[str]:
    raw_keywords = item.get("keywords")
    if isinstance(raw_keywords, list):
        return [str(value) for value in raw_keywords if str(value).strip()]
    text = f"{_requirement_name(item)} {_original_text(item)} {_join(item.get('constraints'))}"
    candidates = ["보안", "성능", "품질", "인터페이스", "데이터", "개인정보", "권한", "로그", "백업", "연계", "배포"]
    return [keyword for keyword in candidates if keyword in text]


def _source_refs(item: dict[str, Any]) -> list[str]:
    for key in ("source", "source_refs", "source_req_ids", "source_requirement_ids"):
        value = item.get(key)
        if isinstance(value, list):
            return [str(ref) for ref in value if str(ref).strip()]
        if value:
            return [str(value)]
    return []


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip())
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values() if str(item).strip())
    return str(value or "").strip()


def _point_id(project_sn: int | None, source_path: str | None, item: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(project_sn or ""),
            str(source_path or ""),
            _requirement_id(item),
            _requirement_name(item),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))
