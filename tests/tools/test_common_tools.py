import tempfile
import unittest
from pathlib import Path

import fitz
from docx import Document

from tools.llm.json_repair import repair_json_text
from tools.llm.llm_client import LLMClient
from tools.llm.response_parser import parse_json_response
from tools.llm.send_api import send_parallel
from tools.parser.docx_parser import parse_docx
from tools.parser.pdf_parser import parse_pdf
from tools.parser.rfp_rule_parser import parse_rfp_requirements
from tools.parser.table_parser import parse_tables
from tools.search.search_router import search
from tools.search.search_schema import SearchRequest
from tools.storage.cleanup_manager import cleanup_paths
from tools.storage.downloader import download_file
from tools.storage.uploader import upload_file


class CommonToolsTest(unittest.TestCase):
    def test_search_router_normalizes_rag_web_both_and_none(self) -> None:
        class FakeQdrant:
            def query_points(self, **kwargs):
                self.kwargs = kwargs
                return type(
                    "Response",
                    (),
                    {
                        "points": [
                            {
                                "id": "rag-1",
                                "score": 0.9,
                                "payload": {"title": "RAG", "text": "rag content"},
                            }
                        ]
                    },
                )()

        def web_provider(query, top_k, filters):
            return [{"id": "web-1", "title": "WEB", "snippet": "web content"}]

        rag = search("query", query_vector=[0.1], rag_client=FakeQdrant())
        web = search("query", search_targets="WEB", web_provider=web_provider)
        both = search(
            "query",
            search_targets="BOTH",
            query_vector=[0.1],
            rag_client=FakeQdrant(),
            web_provider=web_provider,
        )
        none = search("query", search_targets="NONE")

        self.assertEqual(rag["data"]["normalized_results"][0]["source"], "RAG")
        self.assertEqual(rag["data"]["normalized_results"][0]["source_kind"], "RAG")
        self.assertEqual(rag["data"]["search_type"], "RAG")
        self.assertEqual(rag["data"]["results"][0]["metadata"]["title"], "RAG")
        self.assertEqual(web["data"]["normalized_results"][0]["source"], "WEB")
        self.assertEqual(web["data"]["normalized_results"][0]["citation"], "")
        self.assertEqual(web["data"]["search_type"], "WEB")
        self.assertEqual(web["data"]["results"][0]["title"], "WEB")
        self.assertEqual(len(both["data"]["normalized_results"]), 2)
        self.assertEqual(both["data"]["search_type"], "BOTH")
        self.assertEqual(none["data"]["normalized_results"], [])
        self.assertEqual(none["data"]["search_type"], "NONE")

    def test_search_request_validates_contract(self) -> None:
        request = SearchRequest(
            project_sn=1,
            docs_cd="SRS",
            agent_name="requirement_generation_agent",
            search_intent="비기능 요구사항 검색",
            query=" requirements ",
            search_targets="BOTH",
            filters={"requirement_type": ["보안 요구사항"]},
            top_k=10,
        )
        self.assertEqual(request.query, "requirements")
        self.assertEqual(request.project_sn, 1)

    def test_search_router_accepts_request_dict_contract(self) -> None:
        def web_provider(query, top_k, filters):
            self.assertEqual(filters["source_type"], ["POLICY"])
            return [
                {
                    "title": "표준",
                    "url": "https://example.test/standard",
                    "snippet": "standard content",
                    "source": "example",
                    "published_at": "2026-01-01",
                }
            ]

        result = search(
            {
                "project_sn": 1,
                "docs_cd": "SRS",
                "agent_name": "requirement_generation_agent",
                "search_intent": "비기능 요구사항 검색",
                "query": "로그인 보안 정책",
                "search_targets": "WEB",
                "filters": {"source_type": ["POLICY"]},
                "top_k": 5,
            },
            web_provider=web_provider,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["request"]["agent_name"], "requirement_generation_agent")
        self.assertEqual(result["data"]["normalized_results"][0]["source_kind"], "WEB")
        self.assertEqual(
            result["data"]["normalized_results"][0]["citation"],
            "https://example.test/standard",
        )

    def test_llm_client_uses_injected_transport(self) -> None:
        captured = {}

        def transport(url, payload, headers, timeout):
            captured.update(
                {"url": url, "payload": payload, "headers": headers, "timeout": timeout}
            )
            return {"choices": [{"message": {"content": "{}"}}]}

        client = LLMClient(
            base_url="http://llm.test/v1",
            api_key="secret",
            model_name="test-model",
            timeout=10,
            transport=transport,
        )
        result = client.chat([{"role": "user", "content": "hello"}])

        self.assertTrue(result["success"])
        self.assertEqual(captured["url"], "http://llm.test/v1/chat/completions")
        self.assertEqual(captured["payload"]["model"], "test-model")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["timeout"], 10)

    def test_parallel_llm_calls_preserve_input_order(self) -> None:
        def transport(url, payload, headers, timeout):
            return payload["messages"][0]["content"]

        client = LLMClient(transport=transport)
        result = send_parallel(
            [
                {"messages": [{"role": "user", "content": "first"}]},
                {"messages": [{"role": "user", "content": "second"}]},
            ],
            client=client,
            max_workers=2,
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            [item["data"] for item in result["data"]],
            ["first", "second"],
        )

    def test_json_parser_repairs_code_fence_and_trailing_comma(self) -> None:
        result = repair_json_text('```json\n{"value": 1,}\n```')
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["value"], {"value": 1})

        parsed = parse_json_response('{"items": []}')
        self.assertTrue(parsed["success"])

    def test_local_download_upload_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            source = root_path / "source.txt"
            source.write_text("hello", encoding="utf-8")

            download = download_file(
                file_path=str(source),
                file_name="copy.txt",
                destination_dir=str(root_path / "input"),
            )
            self.assertTrue(download["success"])

            upload = upload_file(
                download["data"]["local_file_path"],
                storage_path=str(root_path / "output" / "copy.txt"),
            )
            self.assertTrue(upload["success"])

            cleanup = cleanup_paths(
                [download["data"]["local_file_path"], upload["data"]["storage_file_path"]],
                allowed_root=root,
            )
            self.assertTrue(cleanup["success"])

    def test_docx_parser(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "sample.docx"
            document = Document()
            document.add_paragraph("sample text")
            table = document.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "a"
            table.cell(0, 1).text = "b"
            document.save(path)

            result = parse_docx(str(path))
            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["paragraphs"], ["sample text"])
            self.assertEqual(result["data"]["tables"][0][0], ["a", "b"])

            tables = parse_tables(str(path))
            self.assertTrue(tables["success"])
            self.assertEqual(tables["data"]["tables"][0][0], ["a", "b"])

    def test_rfp_rule_parser_supports_injected_parser(self) -> None:
        result = parse_rfp_requirements(
            "sample.docx",
            parser=lambda file_path: [{"requirement_id": "SFR-001"}],
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["data"]["requirements"],
            [{"requirement_id": "SFR-001"}],
        )

    def test_rfp_rule_parser_extracts_docx_table_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "rfp.docx"
            document = Document()
            table = document.add_table(rows=4, cols=2)
            table.cell(0, 0).text = "요구사항 고유번호"
            table.cell(0, 1).text = "SFR-001"
            table.cell(1, 0).text = "요구사항명"
            table.cell(1, 1).text = "로그인 기능"
            table.cell(2, 0).text = "요구사항 상세설명"
            table.cell(2, 1).text = "사용자는 아이디와 비밀번호로 로그인할 수 있어야 한다."
            table.cell(3, 0).text = "검증기준"
            table.cell(3, 1).text = "정상 로그인 여부를 확인한다."
            document.save(path)

            result = parse_rfp_requirements(str(path))

            self.assertTrue(result["success"])
            item = result["data"]["requirements"][0]
            self.assertEqual(item["requirement_id"], "SFR-001")
            self.assertEqual(item["req_id"], "SFR-001")
            self.assertEqual(item["requirement_name"], "로그인 기능")
            self.assertEqual(item["requirement_type"], "기능")
            self.assertIn("로그인", item["detail_text"])
            self.assertEqual(item["validation_criteria"], ["정상 로그인 여부를 확인한다."])

    def test_pdf_parser(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "sample.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "sample pdf")
            document.save(path)
            document.close()

            result = parse_pdf(str(path))
            self.assertTrue(result["success"])
            self.assertIn("sample pdf", result["data"]["text"])

    def test_standard_error_result(self) -> None:
        result = search("test", search_targets="INVALID")  # type: ignore[arg-type]
        self.assertFalse(result["success"])
        self.assertEqual(
            set(result["error"]),
            {"code", "message", "details"},
        )


if __name__ == "__main__":
    unittest.main()
