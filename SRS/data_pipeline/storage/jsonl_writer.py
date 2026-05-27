import json
import os
from pathlib import Path
from typing import List, Dict, Any, Union
from schemas.chunk_schema import ChunkData

def save_jsonl(data: List[Dict[str, Any]], output_path: str) -> None:
    """
    [기존 로직 유지] 메모리에 쌓인 딕셔너리 리스트를 한 번에 JSONL 파일로 덤프합니다.
    단일 문서 단위의 콤팩트한 저장에 유용합니다.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"✅ JSONL 전체 저장 완료: {output_path}")


class JSONLWriter:
    """
    [실전형 확장 라이터] 
    대용량 가이드라인 문서 대량 전처리 시 메모리 낭비를 방지하기 위해,
    청크 데이터가 생성되는 족족 디스크에 실시간 스트리밍 적재(Append)합니다.
    """
    def __init__(self, output_path: str, overwrite: bool = True):
        self.path = Path(output_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # 덮어쓰기 모드일 경우 기존 파일 선제 삭제
        if overwrite and self.path.exists():
            os.remove(self.path)

    def write_chunk(self, chunk: Union[ChunkData, Dict[str, Any]]) -> None:
        """
        단 하나의 청크 데이터를 JSONL 파일 맨 아래에 실시간으로 이어 붙입니다.
        ChunkData 스키마 객체와 일반 딕셔너리를 모두 지원합니다.
        """
        # 1. 입력 형식이 스키마 객체인 경우 딕셔너리로 자동으로 풀기
        if isinstance(chunk, ChunkData):
            data_dict = chunk.to_dict()
        else:
            data_dict = chunk

        # 2. 파일 끝에 한 줄 추가 (Append 모드)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data_dict, ensure_ascii=False) + "\n")

    def write_all(self, chunks: List[Union[ChunkData, Dict[str, Any]]]) -> None:
        """리스트에 담긴 여러 개의 청크 객체들을 순회하며 안전하게 적재합니다."""
        for chunk in chunks:
            self.write_chunk(chunk)
