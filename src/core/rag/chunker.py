from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config import get_settings

settings = get_settings()

class DocumentChunker:
    def __init__(self, chunk_size: int = None, overlap: int = None):
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.overlap = overlap or settings.RAG_CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk(self, document: Dict[str, Any]) -> List[Dict[str, Any]]:
        content = document["content"]
        chunks = self.splitter.split_text(content)
        return [
            {
                "content": chunk,
                "metadata": {
                    **document["metadata"],
                    "chunk_index": i,
                    "chunk_total": len(chunks),
                    "chunk_size": len(chunk)
                }
            }
            for i, chunk in enumerate(chunks)
        ]