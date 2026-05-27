"""
schemas 패키지 초기화 파일
프로젝트 전반에서 사용되는 데이터 명세 클래스들을 최상위 네임스페이스로 익스포트합니다.
"""

from schemas.parsed_document import ParsedPage, ParsedDocument
from schemas.metadata_schema import MetadataSchema
from schemas.chunk_schema import ChunkData

# 외부에서 패키지를 'from schemas import *' 형태로 긁어갈 때 허용할 클래스 화이트리스트 정의
__all__ = [
    "ParsedPage",
    "ParsedDocument",
    "MetadataSchema",
    "ChunkData"
]
