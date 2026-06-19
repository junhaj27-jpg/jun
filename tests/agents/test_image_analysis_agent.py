import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.image_analysis.agent import ImageAnalysisAgent
from agents.image_analysis.processors.image_analyzer import analyze_images
from tools.result import success_result


class FakeVisionLLM:
    def chat(self, messages, **kwargs):
        content = messages[1]["content"]
        path_text = str(content)
        if "unmapped" in path_text:
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
                "functional_areas": [
                    {
                        "name": "로그인 입력 영역",
                        "visible_texts": ["아이디", "비밀번호"],
                        "area_role": "사용자가 인증 정보를 입력합니다.",
                        "x_ratio": 0.4,
                        "y_ratio": 0.5,
                    }
                ],
                "user_actions": ["로그인"],
                "navigation_candidates": [],
            }
        )


class FakeImageWorkflowLLM:
    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        if "화면 이미지를 분석" in system_prompt:
            return success_result(
                {
                    "screen_name_candidate": "로그인 화면",
                    "purpose": "사용자 로그인",
                    "input_fields": ["아이디", "비밀번호"],
                    "buttons": ["로그인"],
                    "content_areas": [],
                    "functional_areas": [
                        {
                            "name": "로그인 버튼",
                            "visible_texts": ["로그인"],
                            "area_role": "로그인을 실행합니다.",
                            "x_ratio": 0.6,
                            "y_ratio": 0.7,
                        }
                    ],
                    "user_actions": ["로그인"],
                    "navigation_candidates": [],
                }
            )
        if "RAG 검색 Query" in system_prompt:
            return success_result(
                {
                    "ux_query": "로그인 화면 접근성 UI UX 가이드",
                    "interface_query": "로그인 인터페이스 요구사항 화면 정책",
                }
            )
        if "요구사항과 이미지를 매칭" in system_prompt:
            return success_result(
                {
                    "interface_image_analysis_json_list": [
                        {
                            "screen_id": "SCR-001",
                            "screen_name": "로그인 화면",
                            "image_path": "login.png",
                            "image_status": "AVAILABLE",
                            "match_status": "MATCHED",
                            "matched_requirement_ids": ["REQ-001"],
                            "analysis": {"purpose": "사용자 로그인"},
                        }
                    ]
                }
            )
        if "화면 상세 설계" in system_prompt:
            return success_result(
                {
                    "screen_name": "로그인 화면",
                    "screen_type": "인증 화면",
                    "menu_path": "통합 플랫폼 > 인증 > 로그인",
                    "screen_overview": "사용자가 아이디와 비밀번호를 입력하고 로그인 버튼을 눌러 인증을 수행하는 화면입니다.",
                    "process_contents": [
                        {
                            "no": 1,
                            "title": "인증정보 입력",
                            "description": "사용자가 아이디와 비밀번호를 입력하면 시스템은 필수 입력 여부를 확인합니다.",
                            "requirement_basis": "REQ-001 로그인",
                        },
                        {
                            "no": 2,
                            "title": "로그인 실행",
                            "description": "사용자가 로그인 버튼을 클릭하면 시스템은 계정 정보를 검증하고 메인 화면으로 이동합니다.",
                            "requirement_basis": "REQ-001 로그인",
                        },
                    ],
                    "button_markers": [
                        {"no": 1, "target_area": "인증정보 입력", "x_ratio": 0.4, "y_ratio": 0.5},
                        {"no": 2, "target_area": "로그인 실행", "x_ratio": 0.6, "y_ratio": 0.7},
                    ],
                }
            )
        if "description" in system_prompt:
            return success_result({"description": "LLM이 생성한 로그인 화면 설명입니다."})
        if "사용자 인터페이스 구조도" in system_prompt:
            return success_result(
                [
                    {
                        "level1": "통합 플랫폼",
                        "level2": "인증",
                        "level3": "로그인",
                        "level4": "로그인 화면",
                    }
                ]
            )
        return success_result({"content": user_prompt})


class RecordingVisionLLM:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        return success_result(
            {
                "screen_name_candidate": "업로드 화면",
                "purpose": "파일 업로드",
                "input_fields": ["파일"],
                "buttons": ["업로드"],
                "content_areas": [],
                "functional_areas": [
                    {
                        "name": "파일 선택 영역",
                        "visible_texts": ["파일"],
                        "area_role": "업로드할 파일을 선택합니다.",
                        "x_ratio": 0.5,
                        "y_ratio": 0.5,
                    }
                ],
                "user_actions": ["파일 업로드"],
                "navigation_candidates": [],
            }
        )


class ImageAnalysisAgentTest(unittest.TestCase):
    def test_vision_llm_receives_image_url_content(self) -> None:
        with TemporaryDirectory() as root:
            image = Path(root) / "screen.png"
            image.write_bytes(
                bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c6360000002000100ffff03000006000557bfab5d00000000"
                    "49454e44ae426082"
                )
            )
            llm = RecordingVisionLLM()

            analyses, warnings = analyze_images([str(image)], llm_client=llm)

            user_content = llm.messages[0][1]["content"]
            self.assertEqual(analyses[0]["screen_name_candidate"], "업로드 화면")
            self.assertEqual(warnings, [])
            self.assertEqual(user_content[1]["type"], "image_url")
            self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

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
        messages = {
            item["match_status"]: item.get("image_request_message")
            for item in result["interface_image_analysis_json_list"]
        }
        self.assertIn("이미지 추가가 필요합니다", messages["IMAGE_ADD_REQUIRED"])
        self.assertIn("사용 여부 확인", messages["UNMAPPED_IMAGE"])
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
        self.assertIn("이미지 수정이 필요합니다", by_id["SCR-LOGIN"]["image_request_message"])
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

    def test_create_uses_llm_query_matching_and_description_steps(self) -> None:
        search_calls = []

        def search_tool(query, **kwargs):
            search_calls.append((query, kwargs))
            return success_result({"normalized_results": [{"content": query, "score": 0.9}]})

        state = {
            "project_sn": 1,
            "docs_cd": "INTERFACE",
            "udt_yn": "N",
            "input_image_paths": ["login.png"],
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "로그인",
                            "detail_text": "로그인 화면을 제공한다.",
                        }
                    ]
                }
            },
        }

        result = ImageAnalysisAgent(
            llm_client=FakeImageWorkflowLLM(),
            search_tool=search_tool,
        ).execute(state)

        screen = result["interface_image_analysis_json_list"][0]
        self.assertEqual(screen["match_status"], "MATCHED")
        self.assertEqual(screen["description"], "LLM이 생성한 로그인 화면 설명입니다.")
        self.assertEqual(screen["screen_overview"], "사용자가 아이디와 비밀번호를 입력하고 로그인 버튼을 눌러 인증을 수행하는 화면입니다.")
        self.assertEqual(screen["process_contents"][0]["title"], "인증정보 입력")
        self.assertEqual(len(screen["button_markers"]), 2)
        self.assertEqual(result["ui_structure"][0]["level4"], "로그인 화면")
        self.assertIn("로그인 화면 접근성 UI UX 가이드", {call[0] for call in search_calls})
        self.assertIn("로그인 인터페이스 요구사항 화면 정책", {call[0] for call in search_calls})

    def test_llm_match_preserves_vision_process_areas_when_screen_id_changes(self) -> None:
        class ScreenIdChangingLLM(FakeImageWorkflowLLM):
            def chat(self, messages, **kwargs):
                system_prompt = messages[0]["content"]
                if "요구사항과 이미지를 매칭" in system_prompt:
                    return success_result(
                        {
                            "interface_image_analysis_json_list": [
                                {
                                    "screen_id": "SCR-999",
                                    "screen_name": "로그인 화면",
                                    "image_path": "login.png",
                                    "image_status": "AVAILABLE",
                                    "match_status": "MATCHED",
                                    "matched_requirement_ids": ["REQ-001"],
                                    "analysis": {"purpose": "사용자 로그인"},
                                }
                            ]
                        }
                    )
                return super().chat(messages, **kwargs)

        state = {
            "project_sn": 1,
            "docs_cd": "INTERFACE",
            "udt_yn": "N",
            "input_image_paths": ["login.png"],
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "로그인",
                            "detail_text": "로그인 화면을 제공한다.",
                        }
                    ]
                }
            },
        }

        result = ImageAnalysisAgent(
            llm_client=ScreenIdChangingLLM(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
        ).execute(state)

        screen = result["interface_image_analysis_json_list"][0]
        self.assertEqual(screen["screen_id"], "SCR-999")
        self.assertTrue(screen["process_contents"])
        self.assertNotEqual(screen["process_contents"][0]["title"], "화면 설명")
        self.assertEqual(len(screen["process_contents"]), len(screen["button_markers"]))

    def test_create_generates_process_markers_and_annotated_image(self) -> None:
        class MultiAreaVisionLLM:
            def chat(self, messages, **kwargs):
                return success_result(
                    {
                        "screen_name_candidate": "로그인 화면",
                        "purpose": "사용자 로그인",
                        "input_fields": ["아이디", "비밀번호"],
                        "buttons": ["로그인"],
                        "content_areas": [],
                        "functional_areas": [
                            {
                                "name": "아이디 입력 영역",
                                "visible_texts": ["아이디"],
                                "area_role": "아이디를 입력합니다.",
                                "x_ratio": 0.3,
                                "y_ratio": 0.4,
                            },
                            {
                                "name": "비밀번호 입력 영역",
                                "visible_texts": ["비밀번호"],
                                "area_role": "비밀번호를 입력합니다.",
                                "x_ratio": 0.3,
                                "y_ratio": 0.55,
                            },
                            {
                                "name": "로그인 버튼 영역",
                                "visible_texts": ["로그인"],
                                "area_role": "로그인을 실행합니다.",
                                "x_ratio": 0.6,
                                "y_ratio": 0.7,
                            },
                        ],
                        "user_actions": ["로그인"],
                        "navigation_candidates": [],
                    }
                )

        with TemporaryDirectory() as root:
            image = Path(root) / "login.png"
            from PIL import Image

            Image.new("RGB", (100, 100), color="white").save(image)
            state = {
                "project_sn": 1,
                "docs_cd": "INTERFACE",
                "udt_yn": "N",
                "input_image_paths": [str(image)],
                "agent_outputs": {
                    "document_merge_agent": {
                        "integrated_requirement_json_list": [
                            {"req_id": "REQ-001", "req_name": "로그인", "detail_text": "로그인 화면을 제공한다."}
                        ]
                    }
                },
            }

            result = ImageAnalysisAgent(
                llm_client=MultiAreaVisionLLM(),
                search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
            ).execute(state)

            screen = result["interface_image_analysis_json_list"][0]
            self.assertTrue(Path(screen["annotated_image_path"]).exists())
            from PIL import Image

            with Image.open(screen["annotated_image_path"]) as annotated:
                self.assertGreaterEqual(annotated.width, 1800)
            self.assertEqual(screen["process_contents"][0]["no"], screen["button_markers"][0]["no"])
            self.assertIn("x_ratio", screen["button_markers"][0])
            self.assertEqual(len(screen["button_markers"]), 3)
            self.assertEqual(len(screen["process_contents"]), len(screen["button_markers"]))
            self.assertTrue(result["ui_structure"])


if __name__ == "__main__":
    unittest.main()
