# src/core/rag/loader.py
from typing import List, Dict, Any
import fitz  # PyMuPDF
import io


class PDFLoader:
    """PDF document loader."""

    def __init__(self, file_content: bytes, file_name: str, metadata: Dict[str, Any] = None):
        self.file_content = file_content
        self.file_name = file_name
        self.metadata = metadata or {}
        self.doc = fitz.open(stream=file_content, filetype="pdf")

    def load(self) -> List[Dict[str, Any]]:
        """Extract text and metadata from PDF."""
        documents = []
        total_pages = len(self.doc)

        for page_num in range(total_pages):
            page = self.doc[page_num]
            text = page.get_text()

            if not text.strip():
                continue

            documents.append({
                "content": text,
                "metadata": {
                    **self.metadata,
                    "page": page_num + 1,
                    "total_pages": total_pages,
                    "source": self.file_name,
                    "file_name": self.file_name
                }
            })

        return documents

    def get_text(self) -> str:
        """Get full text of the document."""
        full_text = ""
        for page in self.doc:
            full_text += page.get_text()
        return full_text