-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table (for tracking what's indexed)
CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    chunk_count INTEGER DEFAULT 0,
    indexed_at TIMESTAMP DEFAULT NOW()
);

-- Chunks table with embeddings
CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES rag_documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Vector similarity search function
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(1536),
    match_threshold float,
    match_count int
)
RETURNS TABLE(
    id uuid,
    content text,
    metadata jsonb,
    similarity float
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        id,
        content,
        metadata,
        1 - (embedding <=> query_embedding) AS similarity
    FROM rag_chunks
    WHERE (1 - (embedding <=> query_embedding)) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Create index for fast similarity search
CREATE INDEX idx_rag_chunks_embedding ON rag_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- RLS Policies
ALTER TABLE rag_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public documents are viewable by everyone" ON rag_documents
    FOR SELECT USING (true);

CREATE POLICY "Public chunks are viewable by everyone" ON rag_chunks
    FOR SELECT USING (true);