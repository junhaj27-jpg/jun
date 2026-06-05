import json, logging
from graph_builder         import build_graph
from modify_graph          import build_modify_graph
from services.docx_service import generate_docx

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
        path = generate_docx(final, prefix="사용자_요구사항_정의서")
        logger.info("문서 저장: %s", path)
    return {"final_reqs": final, "review_reqs": review}


def modify(existing_reqs, instruction, save_docx=True) -> dict:
    result = modify_graph.invoke({
        "existing_reqs": existing_reqs,
        "instruction":   instruction,
    })
    final  = result.get("final_reqs",  [])
    review = result.get("review_reqs", [])
    logger.info("수정 완료: 전체=%d 검토필요=%d", len(final), len(review))
    if save_docx and final:
        path = generate_docx(final, prefix="사용자_요구사항_정의서_수정")
        logger.info("문서 저장: %s", path)
    return {"final_reqs": final, "review_reqs": review}
