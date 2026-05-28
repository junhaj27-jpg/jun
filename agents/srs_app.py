import json, logging
from agents.srs_graph_builder import build_graph
from agents.srs_modify_graph import build_modify_graph
from generators.srs_docx_service import generate_docx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

graph        = build_graph()
modify_graph = build_modify_graph()


def run(rfp, minutes, existing_reqs=None, save_docx=True, output_docx_path=None) -> dict:
    result = graph.invoke({
        "rfp":           rfp,
        "minutes":       minutes,
        "existing_reqs": existing_reqs or [],
    })
    final  = result.get("final_reqs",  [])
    review = result.get("review_reqs", [])
    logger.info("생성 완료: 전체=%d 검토필요=%d", len(final), len(review))
    result["docx_path"] = None
    if save_docx and final:
        path = generate_docx(
            final,
            prefix="사용자 요구사항 정의서",
            output_path=output_docx_path,
        )   # Agent 1
        logger.info("문서 저장: %s", path)
        result["docx_path"] = path
    elif save_docx:
        logger.warning("DOCX 생성 건너뜀: final_reqs가 비어 있습니다.")
    return result


def modify(existing_reqs: list[dict], instruction: str, save_docx=True, output_docx_path=None) -> dict:
    result = modify_graph.invoke({
        "existing_reqs": existing_reqs,
        "instruction":   instruction,
    })
    final  = result.get("final_reqs",  [])
    review = result.get("review_reqs", [])
    logger.info("수정 완료: 전체=%d 검토필요=%d", len(final), len(review))
    result["docx_path"] = None
    if save_docx and final:
        path = generate_docx(
            final,
            prefix="사용자 요구사항 정의서",
            output_path=output_docx_path,
        )    # Agent 2
        logger.info("문서 저장: %s", path)
        result["docx_path"] = path
    elif save_docx:
        logger.warning("DOCX 생성 건너뜀: final_reqs가 비어 있습니다.")
    return result
