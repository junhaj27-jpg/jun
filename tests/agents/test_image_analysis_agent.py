import unittest

from agents.image_analysis.agent import ImageAnalysisAgent
from tools.result import success_result


class FakeVisionLLM:
    def chat(self, messages, **kwargs):
        path = messages[1]["content"]
        if "unmapped" in path:
            screen_name = "알 수 없는 화면"
            purpose = "알 수 없는 목적"
        else:
            screen_name = "로그인 화면"
            purpose = "사용자 로그인"
        return success_result(
            {
                "screen_name_candidate": screen_name,
                "purpose": purpose,
                "input_fields": ["아이디"],
                "buttons": ["로그인"],
                "content_areas": [],
                "user_actions": ["로그인"],
                "navigation_candidates": [],
            }
        )


class ImageAnalysisAgentTest(unittest.TestCase):
    def test_create_analyzes_images_searches_rag_and_marks_missing_or_unmapped(self) -> None:
        search_calls = []

        def search_tool(query, **kwargs):
            search_calls.append((query, kwargs))
            return success_result(
                {"normalized_results": [{"content": "접근성을 준수해야 한다."}]}
            )

        state = {
            "project_sn": 1,
            "docs_cd": "INTERFACE",
            "udt_yn": "N",
            "input_image_paths": ["login.png", "unmapped.png"],
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "로그인",
                            "detail_text": "로그인 화면을 제공한다.",
                        },
                        {
                            "req_id": "REQ-002",
                            "req_name": "관리자 통계",
                            "detail_text": "관리자 통계 화면을 제공한다.",
                        },
                    ]
                }
            },
        }
        result = ImageAnalysisAgent(
            llm_client=FakeVisionLLM(),
            search_tool=search_tool,
        ).execute(state)

        statuses = {item["match_status"] for item in result["interface_image_analysis_json_list"]}
        self.assertIn("MATCHED", statuses)
        self.assertIn("UNMAPPED_IMAGE", statuses)
        self.assertIn("IMAGE_ADD_REQUIRED", statuses)
        self.assertEqual(len(search_calls), len(result["interface_image_analysis_json_list"]) * 2)
        self.assertTrue(all(call[1]["search_targets"] == "RAG" for call in search_calls))
        self.assertIs(state["agent_outputs"]["image_analysis_agent"], result)
        self.assertNotIn("interface_image_analysis_json_list", state)
        self.assertNotIn("debug", result)

    def test_update_marks_modify_add_and_delete_candidates(self) -> None:
        state = {
            "docs_cd": "INTERFACE",
            "udt_yn": "Y",
            "input_image_paths": ["unmapped.png"],
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_artifact_json_list": [
                        {
                            "screen_id": "SCR-LOGIN",
                            "screen_name": "로그인 화면",
                            "requirement_ids": ["REQ-001"],
                            "input_fields": ["아이디", "휴대폰 번호"],
                        },
                        {
                            "screen_id": "SCR-ADMIN",
                            "screen_name": "관리자 통계 화면",
                            "requirement_ids": ["REQ-002"],
                        },
                    ],
                    "existing_output_image_paths": ["login.png"],
                }
            },
        }
        result = ImageAnalysisAgent(
            llm_client=FakeVisionLLM(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
        ).execute(state)

        by_id = {
            item["screen_id"]: item
            for item in result["interface_image_analysis_json_list"]
        }
        self.assertEqual(by_id["SCR-LOGIN"]["match_status"], "IMAGE_MODIFY_REQUIRED")
        self.assertEqual(by_id["SCR-ADMIN"]["match_status"], "IMAGE_ADD_REQUIRED")
        self.assertIn(
            "IMAGE_DELETE_CANDIDATE",
            {item["match_status"] for item in result["interface_image_analysis_json_list"]},
        )

    def test_update_without_artifact_requests_supervisor_decision(self) -> None:
        result = ImageAnalysisAgent().execute(
            {"docs_cd": "INTERFACE", "udt_yn": "Y", "agent_outputs": {}}
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "NEED_SUPERVISOR_DECISION")

    def test_debug_intermediates_are_optional(self) -> None:
        state = {
            "docs_cd": "INTERFACE",
            "udt_yn": "N",
            "input_image_paths": ["login.png"],
            "etc": {"debug": True},
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {"req_id": "REQ-001", "req_name": "로그인"}
                    ]
                }
            },
        }
        result = ImageAnalysisAgent(
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []})
        ).execute(state)

        self.assertIn("image_analysis_result_list", result["debug"])
        self.assertIn("rag_results", result["debug"])


if __name__ == "__main__":
    unittest.main()
