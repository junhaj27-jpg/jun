import json, logging
from agents.srs_graph_builder import build_graph
from agents.srs_modify_graph import build_modify_graph
from generators.srs_docx_service import generate_docx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

graph        = build_graph()
modify_graph = build_modify_graph()


def run(rfp, minutes, existing_reqs=None, save_docx=True) -> dict:
    result = graph.invoke({
        "rfp":           rfp,
        "minutes":       minutes,
        "existing_reqs": existing_reqs or [],
    })
    final  = result.get("final_reqs",  [])
    review = result.get("review_reqs", [])
    logger.info("생성 완료: 전체=%d 검토필요=%d", len(final), len(review))
    if save_docx and final:
        path = generate_docx(final, prefix="generated")   # Agent 1
        logger.info("문서 저장: %s", path)
    return result


def modify(existing_reqs: list[dict], instruction: str, save_docx=True) -> dict:
    result = modify_graph.invoke({
        "existing_reqs": existing_reqs,
        "instruction":   instruction,
    })
    final  = result.get("final_reqs",  [])
    review = result.get("review_reqs", [])
    logger.info("수정 완료: 전체=%d 검토필요=%d", len(final), len(review))
    if save_docx and final:
        path = generate_docx(final, prefix="modified")    # Agent 2
        logger.info("문서 저장: %s", path)
    return result
