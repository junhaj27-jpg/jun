"""
requirement_parser.py

목적:
  - 공공 SI / RFP 요구사항 청크 구조화
  - 표 기반 + 자연어 기반 Hybrid Parsing
  - Requirement Metadata 추출

지원 형태:
  1. Key-Value 표
     | 요구사항명 | 로그인 기능 |

  2. 구조형 표
     | 기능 요구사항 | SFR-001 | 사용자 로그인 |

  3. 자연어 요구사항
     "시스템은 사용자 인증 기능을 제공하여야 한다"

추출 대상:
  - requirement_id
  - requirement_name
  - requirement_type
  - definition
  - details
  - deliverables
  - constraints
  - infra_specs
"""

import re
from typing import Dict, Any, List


# =========================================================
# Requirement ID Pattern
# =========================================================

PATTERN_STR = r"\b((?:sfr|req|sir|cor|cmr|fqr|sec|per|ast|gcl|isr|dar|wtr|uor|prm|ops|mng)-?\d+|[A-Z]{2,}[-_]?\d{2,5})"

REQ_ID_PATTERN = re.compile(PATTERN_STR, re.IGNORECASE)


# =========================================================
# Requirement Type Normalize
# =========================================================

REQ_TYPE_MAP = {
    "기능 요구사항": "FUNCTIONAL",
    "기능요구사항": "FUNCTIONAL",

    "비기능 요구사항": "NON_FUNCTIONAL",
    "비기능요구사항": "NON_FUNCTIONAL",

    "인터페이스 요구사항": "INTERFACE",
    "인터페이스요구사항": "INTERFACE",

    "데이터 요구사항": "DATA",
    "데이터요구사항": "DATA",

    "보안 요구사항": "SECURITY",
    "보안요구사항": "SECURITY",
}


# =========================================================
# Utils
# =========================================================

def clean_cell(value: str) -> str:

    if not value:
        return ""

    return (
        value.replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .strip()
    )


def normalize_requirement_type(value: str) -> str:

    cleaned = clean_cell(value)

    return REQ_TYPE_MAP.get(cleaned, cleaned)


# =========================================================
# Table Extractor
# =========================================================

def extract_table_rows(text: str) -> List[List[str]]:

    rows = []

    for line in text.split("\n"):

        line = line.strip()

        if not line.startswith("|"):
            continue

        cols = [
            clean_cell(c)
            for c in line.strip("|").split("|")
        ]

        cols = [c for c in cols if c]

        if cols:
            rows.append(cols)

    return rows


# =========================================================
# Infra Spec Extractor
# =========================================================

def extract_infra_specs(text: str) -> Dict[str, Any]:

    specs = {}

    lower = text.lower()

    # GPU
    gpu_patterns = [
        r"(h100|h200|a100|a6000|rtx\s?\d+)",
    ]

    gpus = []

    for pattern in gpu_patterns:

        matches = re.findall(pattern, lower, re.IGNORECASE)

        gpus.extend(matches)

    if gpus:
        specs["gpu"] = sorted(list(set(gpus)))

    # CPU
    cpu_match = re.search(
        r"cpu\s*(?:는)?\s*(\d+)\s*core",
        lower,
        re.IGNORECASE
    )

    if cpu_match:
        specs["cpu_core"] = int(cpu_match.group(1))

    # Memory
    mem_match = re.search(
        r"(?:메모리|memory)\s*(\d+)\s*gb",
        lower,
        re.IGNORECASE
    )

    if mem_match:
        specs["memory_gb"] = int(mem_match.group(1))

    # Storage
    storage_match = re.search(
        r"(\d+)\s*tb",
        lower,
        re.IGNORECASE
    )

    if storage_match:
        specs["storage_tb"] = int(storage_match.group(1))

    return specs


# =========================================================
# Constraint Extractor
# =========================================================

def extract_constraints(text: str) -> List[str]:

    constraints = []

    keywords = [
        "하여야 한다",
        "해야 한다",
        "불가능",
        "제한",
        "준수",
        "의무",
        "금지",
        "반드시",
        "필수",
    ]

    sentences = re.split(r"[.\n]", text)

    for sent in sentences:

        sent = sent.strip()

        if not sent:
            continue

        if any(k in sent for k in keywords):
            constraints.append(sent)

    return sorted(list(set(constraints)))


# =========================================================
# Main Parser
# =========================================================

def parse_requirement(text: str) -> Dict[str, Any]:

    result: Dict[str, Any] = {

        # 기본
        "requirement_id": None,
        "requirement_name": None,
        "requirement_type": None,

        # 상세
        "definition": None,
        "details": None,

        # 부가
        "deliverables": [],
        "constraints": [],
        "infra_specs": {},

        # 메타
        "parsed_from_table": False,
    }

    if not text:
        return result

    rows = extract_table_rows(text)

    # =====================================================
    # TABLE PARSING
    # =====================================================

    if rows:

        result["parsed_from_table"] = True

        for row in rows:

            # ---------------------------------------------
            # 구조형 요구사항 표
            # 예:
            # | 기능 요구사항 | SFR-001 | 로그인 기능 |
            # ---------------------------------------------

            if len(row) >= 3:

                col1 = clean_cell(row[0])
                col2 = clean_cell(row[1])
                col3 = clean_cell(row[2])

                if REQ_ID_PATTERN.search(col2):

                    result["requirement_type"] = (
                        normalize_requirement_type(col1)
                    )

                    result["requirement_id"] = col2

                    result["requirement_name"] = col3

                    if not result["details"]:
                        result["details"] = text[:2000]

            # ---------------------------------------------
            # Key-Value 표
            # ---------------------------------------------

            if len(row) < 2:
                continue

            key = row[0].replace(" ", "")
            value = clean_cell(row[1])

            # 요구사항 ID
            if (
                "요구사항고유번호" in key
                or "요구사항번호" in key
            ):
                result["requirement_id"] = value

            # 요구사항명
            elif (
                "요구사항명칭" in key
                or "요구사항명" in key
            ):
                result["requirement_name"] = value

            # 요구사항 분류
            elif "요구사항분류" in key:

                result["requirement_type"] = (
                    normalize_requirement_type(value)
                )

            # 정의
            elif "정의" == key:
                result["definition"] = value

            # 세부내용
            elif "세부내용" in key:

                if result["details"]:
                    result["details"] += "\n" + value
                else:
                    result["details"] = value

            # 산출정보
            elif "산출정보" in key:

                outputs = [
                    clean_cell(v)
                    for v in re.split(r"[,.]", value)
                    if clean_cell(v)
                ]

                result["deliverables"].extend(outputs)

    # =====================================================
    # FALLBACK REGEX
    # =====================================================

    if not result["requirement_id"]:

        req_match = REQ_ID_PATTERN.search(text)

        if req_match:
            result["requirement_id"] = req_match.group(1)

    # =====================================================
    # Requirement Type Fallback
    # =====================================================

    if not result["requirement_type"]:

        for key in REQ_TYPE_MAP.keys():

            if key in text:

                result["requirement_type"] = (
                    normalize_requirement_type(key)
                )

                break

    # =====================================================
    # Requirement Name Fallback
    # =====================================================

    if not result["requirement_name"]:

        lines = [
            l.strip()
            for l in text.split("\n")
            if l.strip()
        ]

        if lines:
            result["requirement_name"] = lines[0][:200]

    # =====================================================
    # Constraints
    # =====================================================

    result["constraints"] = extract_constraints(text)

    # =====================================================
    # Infra Specs
    # =====================================================

    result["infra_specs"] = extract_infra_specs(text)

    # =====================================================
    # Details Fallback
    # =====================================================

    if not result["details"]:

        cleaned = text.strip()

        if len(cleaned) > 50:
            result["details"] = cleaned[:2000]

    # =====================================================
    # Deliverable Dedup
    # =====================================================

    result["deliverables"] = sorted(
        list(set(result["deliverables"]))
    )

    return result