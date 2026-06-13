import json
import tempfile
import unittest
from pathlib import Path

from agents.document_merge.agent import DocumentMergeAgent
from tools.result import success_result


class FakeLLMClient:
    def chat(self, messages, **kwargs):
        return success_result(
            {
                "meeting_change_items": [
                    {
                        "change_type": "ADD",
                        "item": {"req_id": "REQ-NEW", "name": "추가 요구사항"},
                        "search_targets": "WEB",
                        "search_query": "표준 검색",
                    }
                ]
            }
        )


class DocumentMergeAgentTest(unittest.TestCase):
    def test_srs_create_uses_rfp_parser_meeting_llm_and_search_router(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            meeting = Path(root) / "meeting.txt"
            meeting.write_text("신규 요구사항을 추가한다.", encoding="utf-8")
            search_calls = []

            def rfp_parser(path):
                return success_result(
                    {"requirements": [{"req_id": "REQ-001", "name": "기존"}]}
                )

            def search_tool(query, **kwargs):
                search_calls.append((query, kwargs))
                return success_result(
                    {"normalized_results": [{"source": "WEB", "content": "검색 결과"}]}
                )

            state = {
                "docs_cd": "SRS",
                "udt_yn": "N",
                "base_rfp_path": str(Path(root) / "rfp.pdf"),
                "input_file_paths": [str(meeting)],
                "agent_outputs": {},
            }
            result = DocumentMergeAgent(
                llm_client=FakeLLMClient(),
                rfp_parser=rfp_parser,
                search_tool=search_tool,
            ).execute(state)

            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual(len(result["integrated_requirement_json_list"]), 2)
            self.assertEqual(search_calls[0][1]["search_targets"], "WEB")
            self.assertIs(state["agent_outputs"]["document_merge_agent"], result)
            self.assertNotIn("integrated_requirement_json_list", state)

    def test_other_create_loads_requirements_and_reference_documents(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            requirements = root_path / "requirements.json"
            erd = root_path / "erd.json"
            interface = root_path / "interface.json"
            requirements.write_text(
                json.dumps({"requirement_json_list": [{"req_id": "REQ-001"}]}),
                encoding="utf-8",
            )
            erd.write_text(json.dumps({"tables": [{"table_id": "T1"}]}), encoding="utf-8")
            interface.write_text(
                json.dumps({"screens": [{"screen_id": "SCR-1"}]}), encoding="utf-8"
            )

            db = DocumentMergeAgent().execute(
                {
                    "docs_cd": "DB",
                    "udt_yn": "N",
                    "base_requirement_json_path": str(requirements),
                    "erd_file_path": str(erd),
                }
            )
            ts = DocumentMergeAgent().execute(
                {
                    "docs_cd": "TS",
                    "udt_yn": "N",
                    "base_requirement_json_path": str(requirements),
                    "interface_file_path": str(interface),
                }
            )

            self.assertEqual(db["reference_erd_json_list"], [{"table_id": "T1"}])
            self.assertEqual(ts["reference_interface_json_list"], [{"screen_id": "SCR-1"}])

    def test_update_modes_keep_or_merge_outputs_without_top_level_writes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            existing = root_path / "existing.json"
            meeting = root_path / "meeting.txt"
            existing.write_text(
                json.dumps({"items": [{"id": "A", "name": "기존"}]}),
                encoding="utf-8",
            )
            meeting.write_text("기존 내용을 변경한다.", encoding="utf-8")

            structural_state = {
                "docs_cd": "ARCH",
                "udt_yn": "Y",
                "existing_output_path": str(existing),
                "input_file_paths": [str(meeting)],
            }
            document_state = {
                "docs_cd": "INTERFACE",
                "udt_yn": "Y",
                "existing_output_path": str(existing),
                "input_file_paths": [str(meeting)],
            }
            structural = DocumentMergeAgent().execute(structural_state)
            document = DocumentMergeAgent().execute(document_state)

            self.assertIn("existing_output_raw_json", structural)
            self.assertIn("meeting_change_items", structural)
            self.assertIn("integrated_artifact_json_list", document)
            self.assertNotIn("existing_output_raw_json", document)
            self.assertNotIn("integrated_artifact_json_list", document_state)

    def test_missing_required_input_returns_failed_output_in_agent_outputs(self) -> None:
        state = {"docs_cd": "SRS", "udt_yn": "N"}
        result = DocumentMergeAgent().execute(state)

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_type"], "SRS_RFP_MISSING")
        self.assertEqual(state["agent_outputs"]["document_merge_agent"], result)


if __name__ == "__main__":
    unittest.main()
