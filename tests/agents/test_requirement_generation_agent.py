import unittest

from agents.requirement_generation.agent import RequirementGenerationAgent
from agents.requirement_generation.processors.requirement_refiner import (
    normalize_task3_output,
)
from tools.result import success_result


class FakeLLM:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        system = messages[0]["content"]
        if "RAG query" in system:
            return success_result({"query": "login security validation"})
        if "보강 컬럼" in system or "supplemental SRS columns" in system:
            return success_result(
                {
                    "constraints": ["Lock account after 5 failed login attempts."],
                    "priority": "High",
                    "validation_criteria": ["Verify account lock after 5 failed login attempts."],
                    "status": "",
                    "rag_validation": {"status": "APPLIED", "evidence": ["policy"]},
                }
            )
        return success_result({})


class FakeGoldService:
    def __init__(self) -> None:
        self.calls = []

    def generate_from_dict(self, document, **kwargs):
        self.calls.append((document, kwargs))
        return {
            "output_type": "GOLD_REQUIREMENT_SPECIFICATION",
            "document_id": document["document_id"],
            "document_name": document["document_name"],
            "final_requirement_count": 1,
            "final_requirements": [
                {
                    "gold_id": "GOLD-001",
                    "action_type": "로그인",
                    "requirement_name": "사용자 로그인",
                    "requirement_detail": "사용자는 계정으로 로그인할 수 있어야 한다.",
                    "source_task2_ids": ["T2-000001"],
                    "source_atomic_ids": ["SFR-001::A-001"],
                    "sources": ["SFR-001"],
                    "processing_type": "KEPT",
                    "merge_basis": "단일 기능 요구사항으로 유지",
                }
            ],
            "relation_decisions": [],
            "quality": {"status": "PASS", "fallback_count": 0},
        }


class RequirementGenerationAgentTest(unittest.TestCase):
    def test_generation_uses_gold_service_and_enriches_only_missing_columns(self) -> None:
        llm = FakeLLM()
        gold_service = FakeGoldService()
        search_calls = []

        def search_tool(query, **kwargs):
            search_calls.append((query, kwargs))
            return success_result(
                {
                    "normalized_results": [
                        {
                            "content": "Lock account after 5 failed login attempts.",
                            "score": 0.9,
                            "metadata": {"requirement_id": "NFR-SEC-001"},
                        },
                    ]
                }
            )

        state = _state(debug=False)
        result = RequirementGenerationAgent(
            llm_client=llm,
            search_tool=search_tool,
            gold_service=gold_service,
        ).execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(gold_service.calls), 1)
        gold_input = gold_service.calls[0][0]
        self.assertEqual(gold_input["functional_requirements"][0]["requirement_id"], "SFR-001")
        self.assertEqual(gold_input["functional_requirements"][0]["requirement_definition"], "")
        self.assertEqual(gold_input["scope_reference_requirements"][0]["scope_id"], "NFR-001")
        self.assertEqual(search_calls[0][1]["search_targets"], "RAG")
        self.assertEqual(search_calls[0][1]["filters"]["project_sn"], 1)
        self.assertEqual(search_calls[0][1]["filters"]["doc_type"], "project_non_functional_requirement")
        self.assertEqual(search_calls[0][0], "login security validation")
        self.assertIsNone(search_calls[1][1]["filters"])
        self.assertEqual(len(search_calls), 4)
        self.assertIn("검수기준", search_calls[2][0])
        self.assertEqual(search_calls[2][1]["filters"]["project_sn"], 1)
        self.assertIsNone(search_calls[3][1]["filters"])

        item = result["final_requirement_json_list"][0]
        self.assertEqual(item["requirement_id"], "GOLD-001")
        self.assertEqual(item["requirement_type"], "기능")
        self.assertEqual(item["requirement_name"], "사용자 로그인")
        self.assertEqual(item["description"], "사용자는 계정으로 로그인할 수 있어야 한다.")
        self.assertEqual(item["source"], ["SFR-001", "NFR-SEC-001"])
        self.assertIn("단일 기능 요구사항으로 유지", item["note"])
        self.assertIn("RAG 보강 근거", item["note"])
        self.assertIn("NFR-SEC-001", item["note"])
        self.assertNotIn("action_type", item)
        self.assertNotIn("merge_basis", item)
        self.assertNotIn("req_id", item)
        self.assertNotIn("req_name", item)
        self.assertNotIn("detail_text", item)
        self.assertNotIn("source_req_ids", item)
        self.assertNotIn("source_task2_ids", item)
        self.assertNotIn("source_atomic_ids", item)
        self.assertEqual(item["constraints"], ["Lock account after 5 failed login attempts."])
        self.assertEqual(item["priority"], [])
        self.assertEqual(item["solution"], [])
        self.assertEqual(item["validation_criteria"], ["Verify account lock after 5 failed login attempts."])
        self.assertIs(state["agent_outputs"]["requirement_generation_agent"], result)
        self.assertNotIn("debug", result)

    def test_empty_rag_keeps_gold_without_unrelated_non_functional_fallback(self) -> None:
        result = RequirementGenerationAgent(
            gold_service=FakeGoldService(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
        ).execute(_state())

        item = result["final_requirement_json_list"][0]
        self.assertEqual(item["constraints"], [])
        self.assertEqual(item["priority"], [])
        self.assertEqual(item["solution"], [])
        self.assertEqual(item["validation_criteria"], [])

    def test_rag_failure_keeps_gold_result_and_returns_warning(self) -> None:
        def failed_search(query, **kwargs):
            return {
                "success": False,
                "data": None,
                "error": {"code": "RAG_FAILED", "message": "검색 실패", "details": None},
            }

        result = RequirementGenerationAgent(
            gold_service=FakeGoldService(),
            search_tool=failed_search,
        ).execute(_state())

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["final_requirement_json_list"][0]["requirement_id"], "GOLD-001")
        self.assertEqual(result["warnings"][0]["code"], "REQUIREMENT_RAG_SEARCH_FAILED")

    def test_invalid_mode_and_missing_input_fail(self) -> None:
        invalid = RequirementGenerationAgent(gold_service=FakeGoldService()).execute({"docs_cd": "DB", "udt_yn": "N"})
        missing = RequirementGenerationAgent(gold_service=FakeGoldService()).execute({"docs_cd": "SRS", "udt_yn": "N"})

        self.assertEqual(invalid["failure_type"], "REQUIREMENT_GENERATION_INVALID_MODE")
        self.assertEqual(missing["failure_type"], "INTEGRATED_REQUIREMENT_MISSING")

    def test_debug_contains_gold_and_rag_intermediates(self) -> None:
        result = RequirementGenerationAgent(
            gold_service=FakeGoldService(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
        ).execute(_state(debug=True))

        self.assertIn("debug", result)
        self.assertIn("gold_generation_input", result["debug"])
        self.assertIn("gold_final_requirement_list", result["debug"])
        self.assertIn("rag_searches", result["debug"])

    def test_task3_output_is_normalized_for_cbd_document(self) -> None:
        normalized = normalize_task3_output(
            {
                "final_requirements": [
                    {
                        "gold_id": "GOLD-001",
                        "action_type": "산출",
                        "requirement_name": "CXL 메모리 프레임워크",
                        "requirement_detail": "CXL 메모리 프레임워크를 설계하여야 한다.",
                        "source_task2_ids": ["T2-000001"],
                        "source_atomic_ids": ["SFR-001::SFR-001-001"],
                        "sources": ["SFR-001", "SFR-003"],
                        "processing_type": "통합",
                        "merge_basis": "중복 기능을 통합함.",
                    }
                ]
            }
        )

        item = normalized[0]
        self.assertEqual(item["requirement_id"], "GOLD-001")
        self.assertEqual(item["requirement_type"], "기능")
        self.assertEqual(item["description"], "CXL 메모리 프레임워크를 설계하여야 한다.")
        self.assertEqual(item["source"], ["SFR-001", "SFR-003"])
        self.assertEqual(item["priority"], [])
        self.assertEqual(item["solution"], [])
        self.assertEqual(item["note"], "중복 기능을 통합함.")
        self.assertNotIn("action_type", item)
        self.assertNotIn("merge_basis", item)
        self.assertNotIn("source_task2_ids", item)
        self.assertNotIn("source_atomic_ids", item)


def _state(debug=False):
    return {
        "project_sn": 1,
        "docs_cd": "SRS",
        "udt_yn": "N",
        "base_rfp_path": "C:/SKN24/ALPLED-CORE/data/requirement_sources/RFP/sample.docx",
        "etc": {"debug": debug},
        "agent_outputs": {
            "document_merge_agent": {
                "integrated_requirement_json_list": [
                    {
                        "requirement_id": "SFR-001",
                        "requirement_name": "로그인",
                        "requirement_type": "기능",
                        "requirement_detail": "사용자가 로그인한다.",
                        "source_location": {"table_index": 1},
                    },
                    {
                        "requirement_id": "NFR-001",
                        "requirement_name": "응답시간",
                        "requirement_type": "성능",
                        "requirement_detail": "3초 이내 응답해야 한다.",
                    },
                ]
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
