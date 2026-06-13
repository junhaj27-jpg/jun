"""
parsers 패키지 초기화 파일
다양한 문서 포맷(PDF, DOCX, TEXT)의 구조 보존 파서들을 외부에 일관된 인터페이스로 노출합니다.
"""

import os
from typing import Dict, Any, Callable

def parse_pdf(file_path: str) -> Dict[str, Any]:
    from parsers.pdf_parser import parse_pdf as _parse_pdf
    return _parse_pdf(file_path)


def parse_docx(file_path: str) -> Dict[str, Any]:
    from parsers.docx_parser import parse_docx as _parse_docx
    return _parse_docx(file_path)


def parse_text(file_path: str) -> Dict[str, Any]:
    from parsers.text_parser import parse_text as _parse_text
    return _parse_text(file_path)

_PARSER_MAP: Dict[str, Callable[[str], Dict[str, Any]]] = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".txt": parse_text,
    ".md": parse_text
}

def get_parser_for_file(file_path: str) -> Callable[[str], Dict[str, Any]]:
    """
    [파이프라인 연동 헬퍼]
    입력된 파일의 확장자를 분석하여 가장 적합한 순서 보존 파서 함수를 반환합니다.
    지원하지 않는 포맷일 경우 ValueError를 발생시킵니다.
    """
    _, ext = os.path.splitext(file_path.lower())
    
    if ext not in _PARSER_MAP:
        raise ValueError(f"지원하지 않는 문서 형식입니다 ({ext}): {file_path}")
        
    return _PARSER_MAP[ext]

__all__ = [
    "parse_pdf",
    "parse_docx",
    "parse_text",
    "get_parser_for_file"
]
