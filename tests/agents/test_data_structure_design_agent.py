import unittest

from agents.data_structure_design.agent import DataStructureDesignAgent
from agents.data_structure_design.processors import apply_public_standard_results
from agents.validation.agent import ValidationAgent
from tools.result import success_result


class FakeDataLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        return success_result({"analysis": "ok"})


class FakeStructuredDataLLM:
    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        if "요구사항 그룹 분석" in system_prompt:
            return success_result(
                {
                    "domain_group": {
                        "domain_name": "사용자 관리",
                        "source_requirement_ids": ["REQ-001"],
                        "description": "사용자 관리 도메인",
                    }
                }
            )
        if "엔티티 후보" in system_prompt:
            return success_result(
                {
                    "entity": {
                        "logical_name": "사용자",
                        "description": "사용자 엔티티",
                        "source_requirement_ids": ["REQ-001"],
                    }
                }
            )
        if "테이블 후보" in system_prompt:
            return success_result(
                {
                    "table": {
                        "logical_name": "사용자",
                        "physical_name": "tbl_user",
                        "columns": [
                            {
                                "logical_name": "사용자 번호",
                                "physical_name": "user_sn",
                                "data_type": "BIGINT",
                                "nullable": False,
                                "constraints": ["PK"],
                            }
                        ],
                    }
                }
            )
        if "컬럼 후보" in system_prompt:
            return success_result(
                {
                    "table": {
                        "logical_name": "사용자",
                        "physical_name": "tbl_user",
                        "columns": [
                            {
                                "logical_name": "사용자 번호",
                                "physical_name": "user_sn",
                                "data_type": "BIGINT",
                                "nullable": False,
                                "constraints": ["PK"],
                            },
                            {
                                "logical_name": "사용자 아이디",
                                "physical_name": "user_id",
                                "data_type": "VARCHAR(100)",
                                "nullable": False,
                                "constraints": [],
                            },
                        ],
                    }
                }
            )
        if "PK/FK 관계" in system_prompt:
            return success_result({"relationship_list": []})
        if "ERD JSON" in system_prompt:
            return success_result({})
        if "Mermaid용 ERD" in system_prompt:
            return success_result({"entities": [{"name": "tbl_user", "columns": []}], "relationships": []})
        return success_result({})


class FakeBadNamingDataLLM:
    def chat(self, messages, **kwargs):
        system_prompt = messages[0]["content"]
        if "ERD JSON" in system_prompt:
            return success_result(
                {
                    "tables": [
                        {
                            "table_id": "TABLE-001",
                            "logical_name": "AI 플랫폼",
                            "physical_name": "AI 플랫폼(관리)",
                            "source_requirement_ids": ["REQ-001"],
                            "columns": [
                                {
                                    "column_id": "COL-001-001",
                                    "logical_name": "AI 플랫폼 번호",
                                    "physical_name": "AI 플랫폼 번호",
                                    "data_type": "BIGINT",
                                    "nullable": False,
                                    "constraints": ["PK"],
                                }
                            ],
                        }
                    ],
                    "relationships": [],
                }
            )
        return success_result({})


class DataStructureDesignAgentTest(unittest.TestCase):
    def test_public_standard_rag_results_are_applied_to_erd_columns(self) -> None:
        tables = [
            {
                "table_id": "TABLE-001",
                "entity_id": "ENT-001",
                "logical_name": "거래",
                "physical_name": "tbl_trade",
                "columns": [
                    {
                        "logical_name": "거래일자",
                        "physical_name": "trade_date",
                        "data_type": "VARCHAR(255)",
                        "nullable": False,
                        "constraints": [],
                    },
                    {
                        "logical_name": "비밀번호",
                        "physical_name": "password",
                        "data_type": "VARCHAR(255)",
                        "nullable": False,
                        "constraints": [],
                    },
                ],
            }
        ]
        rag_results = [
            {
                "table_id": "TABLE-001",
                "normalized_results": [
                    {
                        "content": (
                            "번호: 450 | 공통표준용어명: 거래일자 | 공통표준용어영문약어명: DLNG_YMD | "
                            "공통표준도메인명: 연월일C8 | 저장 형식: YYYYMMDD"
                        ),
                        "metadata": {"doc_type": "standard_term", "title": "공통표준용어_450"},
                    },
                    {
                        "content": (
                            "번호: 1185 | 공통표준단어명: 비밀번호 | 공통표준단어영문약어명: PSWD | "
                            "공통표준도메인분류명: 번호"
                        ),
                        "metadata": {"doc_type": "standard_word", "title": "공통표준단어_1185"},
                    },
                ],
            }
        ]

        result = apply_public_standard_results(tables, rag_results)
        columns = {column["logical_name"]: column for column in result[0]["columns"]}

        self.assertEqual(columns["거래일자"]["physical_name"], "dlng_ymd")
        self.assertEqual(columns["거래일자"]["data_type"], "CHAR")
        self.assertEqual(columns["거래일자"]["length"], "8")
        self.assertEqual(columns["비밀번호"]["physical_name"], "pswd")
        self.assertIn("standard_source", columns["비밀번호"])

    def test_erd_column_defaults_and_constraints_are_inferred_like_reference_doc(self) -> None:
        tables = [
            {
                "table_id": "TABLE-001",
                "entity_id": "ENT-001",
                "logical_name": "사용자 그룹 구성원",
                "physical_name": "tbl_user_group_member",
                "columns": [
                    {
                        "logical_name": "구성원 ID",
                        "physical_name": "member_id",
                        "data_type": "BIGINT",
                        "nullable": False,
                        "constraints": ["PK"],
                    },
                    {
                        "logical_name": "그룹 ID",
                        "physical_name": "group_id",
                        "data_type": "BIGINT",
                        "nullable": False,
                        "constraints": ["FK"],
                    },
                    {
                        "logical_name": "사용 여부",
                        "physical_name": "use_yn",
                        "data_type": "CHAR(1)",
                        "nullable": False,
                        "constraints": [],
                    },
                    {
                        "logical_name": "생성 일시",
                        "physical_name": "created_at",
                        "data_type": "TIMESTAMP",
                        "nullable": False,
                        "constraints": [],
                    },
                    {
                        "logical_name": "이메일",
                        "physical_name": "email",
                        "data_type": "VARCHAR(200)",
                        "nullable": False,
                        "constraints": [],
                    },
                ],
            }
        ]

        result = apply_public_standard_results(tables, [])
        columns = {column["physical_name"]: column for column in result[0]["columns"]}

        self.assertEqual(columns["member_id"]["default"], "")
        self.assertIn("AUTO_INCREMENT", columns["member_id"]["constraints"])
        self.assertIn("FK tbl_group", columns["group_id"]["constraints"])
        self.assertEqual(columns["use_yn"]["default"], "Y")
        self.assertIn("Y/N", columns["use_yn"]["constraints"])
        self.assertEqual(columns["created_at"]["default"], "CURRENT_TIMESTAMP")
        self.assertIn("UNIQUE", columns["email"]["constraints"])

    def test_erd_entity_logical_name_prefers_korean_name_over_physical_name(self) -> None:
        from agents.data_structure_design.processors.table_builder import normalize_erd_tables

        tables = normalize_erd_tables(
            [
                {
                    "entity_name": "사용자 그룹",
                    "logical_name": "tbl_user_group",
                    "physical_name": "tbl_user_group",
                    "columns": [
                        {
                            "logical_name": "그룹 ID",
                            "physical_name": "group_id",
                            "data_type": "BIGINT",
                            "nullable": False,
                            "constraints": ["PK"],
                        }
                    ],
                }
            ]
        )

        self.assertEqual(tables[0]["logical_name"], "사용자 그룹")
        self.assertEqual(tables[0]["physical_name"], "tbl_user_group")

    def test_display_column_name_rejects_dash_and_long_sentence(self) -> None:
        from agents.data_structure_design.processors.table_builder import display_column_name

        self.assertEqual(display_column_name("-", "rag_ops_nm", "tbl_rag_ops"), "명")
        self.assertEqual(
            display_column_name(
                "검색증강생성 기본사항 RAG RAGOps 정보를 관리하는 테이블입니다",
                "rag_ops_cn",
                "tbl_rag_ops",
            ),
            "내용",
        )
        self.assertEqual(display_column_name("상태 코드", "rag_ops_stts_cd", "tbl_rag_ops"), "상태코드")

    def test_erd_create_builds_tables_relationships_mermaid_and_uses_rag(self) -> None:
        calls = []

        def search_tool(query, **kwargs):
            calls.append((query, kwargs))
            return success_result({"normalized_results": [{"content": "표준 컬럼명"}]})

        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "사용자 관리",
                            "requirement_type": "기능",
                            "detail_text": "사용자 정보를 관리한다.",
                        },
                        {
                            "req_id": "REQ-002",
                            "req_name": "문서 관리",
                            "requirement_type": "기능",
                            "detail_text": "문서를 관리한다.",
                        },
                        {
                            "req_id": "NFR-001",
                            "req_name": "개인정보 보관",
                            "requirement_type": "비기능",
                            "detail_text": "개인정보 이력을 보관한다.",
                        },
                    ]
                }
            },
        }
        result = DataStructureDesignAgent(search_tool=search_tool).execute(state)

        tables = result["erd_entity_json"]["tables"]
        self.assertEqual(result["status"], "SUCCESS")
        self.assertGreaterEqual(len(tables), 2)
        self.assertTrue(all("PK" in table["columns"][0]["constraints"] for table in tables))
        self.assertTrue(result["erd_entity_json"]["relationships"])
        self.assertTrue(result["erd_mermaid_json"]["entities"])
        self.assertTrue(all(call[1]["search_targets"] == "RAG" for call in calls))
        project_requirement_filters = [
            kwargs["filters"]
            for _, kwargs in calls
            if kwargs["filters"].get("project_sn") == 1
        ]
        self.assertTrue(project_requirement_filters)
        self.assertTrue(
            all(
                filters == {
                    "project_sn": 1,
                    "doc_type": "project_non_functional_requirement",
                    "domain": "requirements",
                    "chunk_type": "project_requirement_source",
                }
                for filters in project_requirement_filters
            )
        )
        self.assertIs(state["agent_outputs"]["data_structure_design_agent"], result)
        self.assertNotIn("erd_entity_json", state)

    def test_erd_create_uses_stepwise_requirement_to_table_pipeline(self) -> None:
        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "etc": {"debug": True},
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "requirement_id": "DAR-002",
                            "requirement_type": "데이터 요구사항",
                            "requirement_name": "문서 승인 기반 RAG 학습 자동화",
                            "detail": "사용자 문서 등록 신청, 운영자 승인/반려, chunking, embedding, 처리상태 관리",
                        }
                    ]
                }
            },
        }

        result = DataStructureDesignAgent(
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []})
        ).execute(state)
        tables = {table["table_name"]: table for table in result["erd_entity_json"]["tables"]}

        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("tbl_document", tables)
        self.assertIn("tbl_document_file", tables)
        self.assertIn("tbl_approval", tables)
        self.assertIn("tbl_document_chunk", tables)
        self.assertIn("tbl_embedding_index", tables)
        self.assertIn("tbl_rag_job", tables)
        self.assertIn("tbl_rag_job_step", tables)
        self.assertTrue(all(table["source_requirement_ids"] for table in tables.values()))
        self.assertTrue(any(rel["to_table"] == "tbl_document" for rel in result["erd_entity_json"]["relationships"]))
        self.assertEqual(result["debug"]["validation_result"]["is_valid"], True)
        self.assertEqual(
            result["debug"]["data_structure_intermediate"][0]["requirement_id"],
            "DAR-002",
        )

    def test_erd_create_does_not_add_ai_platform_tables_without_domain_keywords(self) -> None:
        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "etc": {"debug": True},
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "requirement_id": "REQ-PORTAL-001",
                            "requirement_type": "기능 요구사항",
                            "requirement_name": "문서 신청 승인 관리",
                            "detail": "사용자는 문서를 등록 신청하고 관리자는 승인 또는 반려할 수 있어야 한다.",
                        }
                    ]
                }
            },
        }

        result = DataStructureDesignAgent(
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []})
        ).execute(state)
        table_names = {table["table_name"] for table in result["erd_entity_json"]["tables"]}

        self.assertIn("tbl_document", table_names)
        self.assertIn("tbl_approval", table_names)
        self.assertNotIn("tbl_ai_model", table_names)
        self.assertNotIn("tbl_agent", table_names)
        self.assertNotIn("tbl_prompt_template", table_names)
        self.assertNotIn("tbl_rag_job", table_names)
        self.assertEqual(result["debug"]["domain_info"]["primary_domain"], "GENERAL")

    def test_erd_update_preserves_existing_and_adds_meeting_entity(self) -> None:
        state = {
            "docs_cd": "ERD",
            "udt_yn": "Y",
            "agent_outputs": {
                "document_merge_agent": {
                    "existing_output_raw_json": {
                        "tables": [{"logical_name": "사용자", "physical_name": "tbl_user"}]
                    },
                    "meeting_change_items": [
                        {
                            "change_type": "ADD",
                            "item": {"logical_name": "문서", "physical_name": "tbl_docs"},
                        }
                    ],
                }
            },
        }
        result = DataStructureDesignAgent().execute(state)
        names = {table["physical_name"] for table in result["erd_entity_json"]["tables"]}

        self.assertEqual(names, {"tbl_user", "tbl_docs"})
        self.assertTrue(result["erd_mermaid_json"]["entities"])

    def test_erd_update_extracts_tables_from_nested_existing_docx_parse_result(self) -> None:
        state = {
            "docs_cd": "ERD",
            "udt_yn": "Y",
            "agent_outputs": {
                "document_merge_agent": {
                    "existing_output_raw_json": {
                        "file_path": "existing.docx",
                        "raw_json": {
                            "erd_entity_json": {
                                "tables": [
                                    {
                                        "logical_name": "사용자",
                                        "physical_name": "tbl_user",
                                        "columns": [
                                            {
                                                "logical_name": "사용자 ID",
                                                "physical_name": "user_id",
                                                "data_type": "BIGINT",
                                                "nullable": False,
                                                "constraints": ["PK"],
                                            }
                                        ],
                                    }
                                ]
                            }
                        },
                    },
                    "meeting_change_items": [],
                }
            },
        }

        result = DataStructureDesignAgent().execute(state)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["erd_mermaid_json"]["entities"][0]["name"], "tbl_user")

    def test_erd_create_uses_parallel_llm_domain_entity_table_and_column_stages(self) -> None:
        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "사용자 관리",
                            "requirement_type": "기능",
                            "detail_text": "사용자를 관리한다.",
                        }
                    ]
                }
            },
        }
        result = DataStructureDesignAgent(
            llm_client=FakeStructuredDataLLM(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": [{"content": "user_id", "score": 0.9}]}),
        ).execute(state)

        table = result["erd_entity_json"]["tables"][0]
        self.assertEqual(table["physical_name"], "tbl_user")
        self.assertIn("user_id", {column["physical_name"] for column in table["columns"]})
        self.assertEqual(result["erd_mermaid_json"]["entities"][0]["name"], "tbl_user")

    def test_erd_create_standardizes_bad_llm_physical_names_before_validation(self) -> None:
        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "AI 플랫폼 관리",
                            "requirement_type": "기능",
                            "detail_text": "AI 플랫폼 데이터를 관리한다.",
                        }
                    ]
                },
                "mermaid_generation_agent": {
                    "mermaid_code": "erDiagram",
                    "mermaid_image_path": "erd.png",
                },
            },
        }
        DataStructureDesignAgent(
            llm_client=FakeBadNamingDataLLM(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
        ).execute(state)
        validation = ValidationAgent().execute(state)
        table = state["agent_outputs"]["data_structure_design_agent"]["erd_entity_json"]["tables"][0]

        self.assertEqual(table["physical_name"], "tbl_ai_management")
        self.assertEqual(table["columns"][0]["physical_name"], "ai_sn")
        self.assertEqual(validation["validation_result"]["validation_status"], "PASS")

    def test_erd_descriptions_are_standardized_for_document_output(self) -> None:
        noisy_description = "※ 상세 설명:\n- 사용자 로그인, 권한, 세션, 개인정보, 이력 등 모든 근거를 장황하게 나열함;;"
        state = {
            "project_sn": 1,
            "docs_cd": "ERD",
            "udt_yn": "N",
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_requirement_json_list": [
                        {
                            "req_id": "REQ-001",
                            "req_name": "사용자 관리",
                            "requirement_type": "기능",
                            "detail_text": "사용자를 관리한다.",
                        }
                    ]
                }
            },
        }

        class LongDescriptionLLM(FakeStructuredDataLLM):
            def chat(self, messages, **kwargs):
                content = messages[0]["content"]
                if "엔티티별 테이블 후보" in content:
                    return success_result(
                        {
                            "table_candidate_list": [
                                {
                                    "logical_name": "사용자",
                                    "physical_name": "tbl_user",
                                    "description": noisy_description,
                                    "columns": [
                                        {
                                            "logical_name": "사용자 번호",
                                            "physical_name": "user_sn",
                                            "data_type": "BIGINT",
                                            "nullable": False,
                                            "constraints": ["PK"],
                                            "description": noisy_description,
                                        }
                                    ],
                                }
                            ]
                        }
                    )
                return super().chat(messages, **kwargs)

        result = DataStructureDesignAgent(
            llm_client=LongDescriptionLLM(),
            search_tool=lambda query, **kwargs: success_result({"normalized_results": []}),
        ).execute(state)
        table = result["erd_entity_json"]["tables"][0]

        self.assertEqual(table["description"], "사용자 정보를 관리하는 테이블입니다.")
        self.assertEqual(table["table_description"], "사용자 정보를 관리하는 테이블입니다.")
        self.assertLessEqual(len(table["columns"][0]["description"]), 80)

    def test_erd_table_description_ignores_llm_noise(self) -> None:
        from agents.data_structure_design.processors.table_builder import normalize_erd_tables

        tables = normalize_erd_tables(
            [
                {
                    "logical_name": "사용자 정보",
                    "physical_name": "tbl_user",
                    "description": "★ 근거: 요구사항 A/B/C\n1) 로그인 처리\n2) 권한 처리\n- 장황한 설명",
                    "columns": [
                        {
                            "logical_name": "사용자 번호",
                            "physical_name": "user_sn",
                            "data_type": "BIGINT",
                            "nullable": False,
                            "constraints": ["PK"],
                        }
                    ],
                }
            ]
        )

        self.assertEqual(tables[0]["description"], "사용자 정보를 관리하는 테이블입니다.")
        self.assertEqual(tables[0]["table_description"], "사용자 정보를 관리하는 테이블입니다.")

    def test_erd_column_constraints_keep_only_actual_constraints(self) -> None:
        from agents.data_structure_design.processors.table_builder import normalize_erd_tables

        tables = normalize_erd_tables(
            [
                {
                    "logical_name": "사용자",
                    "physical_name": "tbl_user",
                    "columns": [
                        {
                            "logical_name": "사용자 번호",
                            "physical_name": "user_sn",
                            "data_type": "BIGINT",
                            "nullable": False,
                            "constraints": ["PK", "사용자 고유 식별자"],
                        },
                        {
                            "logical_name": "사용자명",
                            "physical_name": "user_nm",
                            "data_type": "VARCHAR(100)",
                            "nullable": False,
                            "constraints": ["사용자 명칭"],
                        },
                        {
                            "logical_name": "비밀번호",
                            "physical_name": "password_hash",
                            "data_type": "VARCHAR(255)",
                            "nullable": False,
                            "constraints": ["비밀번호는 해시로 저장해야 한다."],
                        },
                    ],
                }
            ]
        )

        columns = {column["physical_name"]: column for column in tables[0]["columns"]}

        self.assertEqual(columns["user_sn"]["constraints"], ["PK"])
        self.assertEqual(columns["user_nm"]["constraints"], [])
        self.assertEqual(columns["password_hash"]["constraints"], ["비밀번호는 해시로 저장해야 한다."])

    def test_db_create_converts_reference_erd_and_passes_db_validator(self) -> None:
        state = {
            "docs_cd": "DB",
            "udt_yn": "N",
            "agent_outputs": {
                "document_merge_agent": {
                    "reference_erd_json_list": [
                        {
                            "table_id": "T1",
                            "logical_name": "사용자",
                            "physical_name": "tbl_user",
                            "columns": [
                                {
                                    "column_id": "C1",
                                    "logical_name": "사용자 번호",
                                    "physical_name": "user_sn",
                                    "data_type": "BIGINT",
                                    "nullable": False,
                                    "constraints": ["PK"],
                                }
                            ],
                        }
                    ]
                }
            },
        }
        result = DataStructureDesignAgent().execute(state)
        validation = ValidationAgent().execute(state)

        self.assertEqual(result["db_design_json"]["tables"][0]["table_name"], "tbl_user")
        table = result["db_design_json"]["tables"][0]
        self.assertEqual(table["table_id"], "tbl_user")
        self.assertEqual(table["table_logical_name"], "사용자")
        self.assertEqual(table["initial_count"], "0")
        self.assertEqual(table["daily_growth"], "산정 필요")
        self.assertEqual(table["retention_period"], "업무 기준에 따름")
        self.assertEqual(table["max_count"], "산정 필요")
        self.assertEqual(table["capacity"], "산정 필요")
        self.assertEqual(table["columns"][0]["column_id"], "user_sn")
        self.assertEqual(table["columns"][0]["column_logical_name"], "ID")
        self.assertEqual(table["columns"][0]["pk"], "Y")
        self.assertEqual(validation["validation_result"]["validation_status"], "PASS")

    def test_db_create_preserves_reference_erd_column_names_after_standard_rag(self) -> None:
        def fake_search(*args, **kwargs):
            return {
                "success": True,
                "data": {
                    "normalized_results": [
                        {
                            "source_kind": "RAG",
                            "title": "표준용어",
                            "content": (
                                "공통표준용어명: 사용자 번호 | "
                                "공통표준용어영문약어명: usr_no | "
                                "데이터타입: VARCHAR | "
                                "저장 형식: 20자리"
                            ),
                            "score": 0.99,
                            "metadata": {"doc_type": "standard_term"},
                            "citation": "standard:user_no",
                        }
                    ]
                },
            }

        state = {
            "project_sn": 1,
            "docs_cd": "DB",
            "udt_yn": "N",
            "agent_outputs": {
                "document_merge_agent": {
                    "reference_erd_json_list": [
                        {
                            "table_id": "T1",
                            "logical_name": "사용자",
                            "physical_name": "tbl_user",
                            "columns": [
                                {
                                    "column_id": "C1",
                                    "logical_name": "사용자 번호",
                                    "physical_name": "user_sn",
                                    "data_type": "BIGINT",
                                    "nullable": False,
                                    "constraints": ["PK"],
                                },
                                {
                                    "column_id": "C2",
                                    "logical_name": "사용자 명",
                                    "physical_name": "user_nm",
                                    "data_type": "VARCHAR(100)",
                                    "nullable": False,
                                    "constraints": [],
                                },
                            ],
                        }
                    ]
                }
            },
        }

        result = DataStructureDesignAgent(search_tool=fake_search).execute(state)
        validation = ValidationAgent().execute(state)
        columns = {
            column["column_name"]
            for column in result["db_design_json"]["tables"][0]["columns"]
        }

        self.assertIn("user_sn", columns)
        self.assertIn("user_nm", columns)
        self.assertEqual(validation["validation_result"]["validation_status"], "PASS")

    def test_db_update_normalizes_nested_artifact_and_debug_is_optional(self) -> None:
        state = {
            "docs_cd": "DB",
            "udt_yn": "Y",
            "etc": {"debug": True},
            "agent_outputs": {
                "document_merge_agent": {
                    "integrated_artifact_json_list": [
                        {
                            "tables": [
                                {
                                    "table_name": "tbl_docs",
                                    "table_description": "문서",
                                    "columns": [
                                        {
                                            "column_name": "docs_sn",
                                            "data_type": "BIGINT",
                                            "nullable": False,
                                            "default": None,
                                            "description": "문서 번호",
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            },
        }
        result = DataStructureDesignAgent().execute(state)

        self.assertEqual(result["db_design_json"]["tables"][0]["table_name"], "tbl_docs")
        self.assertIn("source_artifacts", result["debug"])

    def test_missing_inputs_fail(self) -> None:
        erd = DataStructureDesignAgent().execute({"docs_cd": "ERD", "udt_yn": "N"})
        db = DataStructureDesignAgent().execute({"docs_cd": "DB", "udt_yn": "N"})

        self.assertEqual(erd["failure_type"], "ERD_REQUIREMENT_MISSING")
        self.assertEqual(db["failure_type"], "DB_REFERENCE_ERD_MISSING")

    def test_parallel_llm_analysis_is_used_when_client_is_injected(self) -> None:
        llm = FakeDataLLM()
        state = {
            "docs_cd": "DB",
            "udt_yn": "N",
            "etc": {"debug": True},
            "agent_outputs": {
                "document_merge_agent": {
                    "reference_erd_json_list": [
                        {"logical_name": "사용자", "physical_name": "tbl_user"}
                    ]
                }
            },
        }
        result = DataStructureDesignAgent(llm_client=llm).execute(state)

        self.assertGreaterEqual(llm.calls, 3)
        self.assertEqual(result["debug"]["llm_analysis"], {"analysis": "ok"})


if __name__ == "__main__":
    unittest.main()
