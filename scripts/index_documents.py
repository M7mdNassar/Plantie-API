# scripts/index_documents.py
"""
ONE-TIME INDEXING SCRIPT
Run this ONCE when you first set up the AI backend.
It will process all PDFs in the ./pdfs folder and index them in Supabase.
"""

import os
import sys
from pathlib import Path

# Add project root to Python path so 'src' can be imported
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import fitz
from supabase import create_client
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.core.rag.embedder import Embedder
from src.config import get_settings

# Load settings
settings = get_settings()

# Initialize embedder and Supabase client
embedder = Embedder()
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def load_pdf(pdf_path: str) -> str:
    """Extract text from PDF."""
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text


def index_pdf(pdf_path: str):
    """Index a single PDF document."""
    file_name = Path(pdf_path).name
    print(f"📄 Processing: {file_name}")

    # Extract text
    text = load_pdf(pdf_path)
    print(f"   ✅ Extracted {len(text)} characters")

    # Chunk
    chunks = splitter.split_text(text)
    chunk_objects = [
        {
            "content": chunk,
            "metadata": {"source": file_name, "chunk_index": i, "chunk_total": len(chunks)}
        }
        for i, chunk in enumerate(chunks)
    ]
    print(f"   ✅ Created {len(chunks)} chunks")

    # Generate embeddings using Gemini
    contents = [c["content"] for c in chunk_objects]
    embeddings = embedder.get_embeddings_batch(contents)

    for chunk, emb in zip(chunk_objects, embeddings):
        chunk["embedding"] = emb

    # Insert document record
    doc_res = supabase.table("rag_documents").insert({
        "file_name": file_name,
        "metadata": {"source": file_name},
        "chunk_count": len(chunks)
    }).execute()
    doc_id = doc_res.data[0]["id"]

    # Insert chunks
    chunk_data = []
    for chunk in chunk_objects:
        chunk_data.append({
            "document_id": doc_id,
            "content": chunk["content"],
            "metadata": chunk["metadata"],
            "embedding": chunk["embedding"]
        })

    batch_size = 50
    for i in range(0, len(chunk_data), batch_size):
        batch = chunk_data[i:i + batch_size]
        supabase.table("rag_chunks").insert(batch).execute()
        print(f"   ✅ Inserted {min(i + batch_size, len(chunk_data))}/{len(chunk_data)} chunks")

    print(f"   ✅ Done: {file_name}\n")


def main():
    pdf_dir = Path("./pdfs")
    if not pdf_dir.exists():
        print("❌ ./pdfs folder not found. Creating...")
        pdf_dir.mkdir()
        print("   Please place your PDFs in the ./pdfs folder and run again.")
        return

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print("❌ No PDFs found in ./pdfs folder")
        return

    print(f"📚 Found {len(pdf_files)} PDF files to index")
    print("=" * 50)
    for pdf_file in pdf_files:
        try:
            index_pdf(str(pdf_file))
        except Exception as e:
            print(f"❌ Error processing {pdf_file.name}: {e}")

    print("=" * 50)
    print("✅ Indexing complete!")


if __name__ == "__main__":
    main()