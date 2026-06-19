import unittest

from agents.architecture_analysis.agent import ArchitectureAnalysisAgent
from agents.validation.agent import ValidationAgent
from tools.result import success_result


class FakeArchitectureRepository:
    def find_by_project_sn(self, project_sn):
        return {
            "deployment_environment": "cloud",
            "dbms": "PostgreSQL",
            "file_storage": "S3",
            "vector_db": "Qdrant",
            "llm_server": "vLLM",
            "external_systems": ["외부 API"],
        }


class FakeArchitectureLLM:
    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        if "RAG 검색 Query" in system_prompt:
            return success_result({"query": "아키텍처 보안 성능 운영 연계 배포 요구사항", "filters": {"category": "architecture"}})
        if "Driver" in system_prompt:
            return success_result(
                {
                    "drivers": [
                        {"driver_id": "DRV-SEC", "category": "security", "name": "보안 Driver"},
                        {"driver_id": "DRV-PERF", "category": "performance", "name": "성능 Driver"},
                    ]
                }
            )
        if "컴포넌트 후보" in system_prompt:
            return success_result(
                {
                    "components": [
                        {"component_id": "WEB", "name": "Web Client", "layer": "Presentation Layer"},
                        {"component_id": "API", "name": "API Server", "layer": "Application Layer"},
                        {"component_id": "RDBMS", "name": "RDBMS", "layer": "Data Layer"},
                    ]
                }
            )
        if "컴포넌트 간 관계" in system_prompt:
            return success_result(
                {
                    "relations": [
                        {"source": "WEB", "target": "API", "description": "API 호출"},
                        {"source": "API", "target": "RDBMS", "description": "DB 조회"},
                    ]
                }
            )
        if "계층 구조" in system_prompt:
            return success_result(
                {
                    "layers": [
                        {"layer_id": "L1", "name": "Presentation Layer", "component_ids": ["WEB"]},
                        {"layer_id": "L2", "name": "Application Layer", "component_ids": ["API"]},
                        {"layer_id": "L3", "name": "Data Layer", "component_ids": ["RDBMS"]},
                    ]
                }
            )
        if "회의록 변경사항별" in system_prompt:
            return success_result({"impact": "Redis 캐시 추가"})
        return success_result({})


class ArchitectureAnalysisAgentTest(unittest.TestCase):
    def test_create_builds_architecture_from_requirements_config_and_rag(self) -> None:
        search_calls = []

        def search_tool(query, **kwargs):
            search_calls.append(query)
            return success_result(
                {
                    "normalized_results": [
                        {"content": "보안 성능 운영 연계 배포 요구사항", "score": 0.9},
                        {"content": "관련도 낮음", "score": 0.1},
                    ]
                }
            )

        state = _create_state()
        result = ArchitectureAnalysisAgent(
            search_tool=search_tool,
            architecture_config_repository=FakeArchitectureRepository(),
        ).execute(state)

        structure = result["architecture_structure_json"]
        document = result["architecture_document_json"]
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(structure["components"])
        self.assertTrue(structure["relations"])
        self.assertTrue(structure["layers"])
        self.assertEqual(structure["deployment_environment"]["dbms"], "PostgreSQL")
        self.assertTrue(structure["architecture_config_reflected"])
        self.assertTrue(document["requirement_implementations"])
        self.assertIn("보안 성능 운영 연계 배포 요구사항", document["requirement_implementations"][0]["description"])
        self.assertIn("RAG로 확인한 비기능 근거", document["requirement_implementations"][0]["implementation"])
        self.assertEqual(len(search_calls), 7)
        self.assertIs(state["agent_outputs"]["architecture_analysis_agent"], result)
        self.assertNotIn("architecture_structure_json", state)

    def test_create_uses_llm_query_component_relation_and_layer_stages(self) -> None:
        search_queries = []

        def search_tool(query, **kwargs):
            search_queries.append(query["query"])
            return success_result({"normalized_results": [{"content": query["query"], "score": 0.8}]})

        result = ArchitectureAnalysisAgent(
            llm_client=FakeArchitectureLLM(),
            search_tool=search_tool,
            architecture_config_repository=FakeArchitectureRepository(),
        ).execute(_create_state())

        structure = result["architecture_structure_json"]
        self.assertEqual([item["component_id"] for item in structure["components"]], ["WEB", "API", "RDBMS"])
        self.assertEqual(structure["relations"][0]["source"], "WEB")
        self.assertEqual(structure["layers"][0]["name"], "Presentation Layer")
        self.assertIn("아키텍처 보안 성능 운영 연계 배포 요구사항", search_queries)

    def test_update_applies_meeting_changes_and_keeps_config_priority(self) -> None:
        state = {
            "project_sn": 1,
            "docs_cd": "ARCH",
            "udt_yn": "Y",
            "etc": {"architecture_config": {"deployment_environment": "on-premise", "dbms": "Oracle"}},
            "agent_outputs": {
                "document_merge_agent": {
                    "existing_output_raw_json": {
                        "components": [
                            {"component_id": "WEB", "name": "Web Client", "layer": "Presentation Layer"},
                            {"component_id": "API", "name": "API Server", "layer": "Application Layer"},
                        ],
                        "relations": [{"source": "WEB", "target": "API"}],
                    },
                    "meeting_change_items": [
                        {"change_type": "ADD", "item": {"component_id": "REDIS", "name": "Redis Cache", "layer": "Data Layer"}}
                    ],
                }
            },
        }

        result = ArchitectureAnalysisAgent(llm_client=FakeArchitectureLLM()).execute(state)
        structure = result["architecture_structure_json"]

        self.assertIn("REDIS", {component["component_id"] for component in structure["components"]})
        self.assertEqual(structure["deployment_environment"]["dbms"], "Oracle")
        self.assertEqual(result["architecture_document_json"]["meeting_change_items"][0]["change_type"], "ADD")

    def test_created_output_passes_arch_validator_when_mermaid_exists(self) -> None:
        state = _create_state()
        ArchitectureAnalysisAgent(architecture_config_repository=FakeArchitectureRepository()).execute(state)
        state["agent_outputs"]["mermaid_generation_agent"] = {
            "mermaid_code": "flowchart TD\nWEB --> API",
            "mermaid_image_path": "arch.png",
        }
        validation = ValidationAgent().execute(state)

        self.assertEqual(validation["validation_result"]["validation_status"], "PASS")

    def test_missing_inputs_fail(self) -> None:
        result = ArchitectureAnalysisAgent().execute({"docs_cd": "ARCH", "udt_yn": "N"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "ARCH_REQUIREMENT_MISSING")


def _create_state():
    return {
        "project_sn": 1,
        "docs_cd": "ARCH",
        "udt_yn": "N",
        "agent_outputs": {
            "document_merge_agent": {
                "integrated_requirement_json_list": [
                    {
                        "req_id": "REQ-001",
                        "requirement_type": "기능",
                        "req_name": "문서 생성",
                        "detail_text": "사용자는 산출물을 생성할 수 있어야 한다.",
                    },
                    {
                        "req_id": "NFR-001",
                        "requirement_type": "보안 요구사항",
                        "detail_text": "인증, 권한, 암호화를 적용해야 한다.",
                    },
                ]
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
