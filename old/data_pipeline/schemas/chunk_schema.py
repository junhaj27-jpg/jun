# schemas/chunk_schema.py 내부 모습
from dataclasses import dataclass
from typing import Dict, Any
from schemas.metadata_schema import MetadataSchema

@dataclass
class ChunkData:
    chunk_id: str
    page_content: str
    metadata: MetadataSchema 

    @classmethod
    def from_values(cls, chunk_id: str, content: str, meta_dict: Dict[str, Any]) -> "ChunkData":
        return cls(
            chunk_id=chunk_id,
            page_content=content,
            metadata=MetadataSchema.from_dict(meta_dict) # 바인딩 위임
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "page_content": self.page_content,
            "metadata": self.metadata.to_dict()
        }
