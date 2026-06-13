from dataclasses import dataclass, asdict
from typing import List, Dict, Any

@dataclass
class ParsedPage:
    page_number: int
    text: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParsedPage":
        """딕셔너리 데이터를 ParsedPage 객체로 안전하게 변환합니다."""
        return cls(
            page_number=data.get("page_number", 1),
            text=data.get("text", "")
        )

@dataclass
class ParsedDocument:
    text: str
    pages: List[ParsedPage]
    source_path: str
    source_name: str
    document_type: str  # PDF, DOCX, TEXT 등

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParsedDocument":
        """
        [실전용 통합 엔트리] 
        각 파서가 뱉어낸 Dictionary 데이터를 ParsedDocument 객체 체계로 바인딩합니다.
        Key가 누락되어 파이프라인이 멈추는 에러를 원천 차단합니다.
        """
        # pages 내부의 딕셔너리들을 ParsedPage 인스턴스로 변환
        raw_pages = data.get("pages", [])
        parsed_pages = [
            ParsedPage.from_dict(p) if isinstance(p, dict) else p 
            for p in raw_pages
        ]
        
        return cls(
            text=data.get("text", ""),
            pages=parsed_pages,
            source_path=data.get("source_path", ""),
            source_name=data.get("source_name", ""),
            document_type=data.get("document_type", "UNKNOWN")
        )

    def to_dict(self) -> Dict[str, Any]:
        """객체를 JSONL 저장이나 디버깅이 용이한 순수 파이썬 딕셔너리로 변환합니다."""
        return asdict(self)
