-- ==============================================================================
-- Esquema PostgreSQL do Enterprise Document & Data Assistant.
-- Define tabelas, busca vetorial com pgvector e histórico de conversas.
-- ==============================================================================

-- 1. Habilita a extensão pgvector para busca por embeddings.
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Registra metadados de PDFs, planilhas e arquivos CSV.
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('excel', 'csv', 'pdf')),
    file_size_bytes BIGINT NOT NULL,
    storage_path TEXT,
    -- Armazena os metadados das planilhas ou o resumo das páginas do PDF.
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Índices para ordenar documentos recentes e filtrar pelo tipo.
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON public.documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_file_type ON public.documents (file_type);

-- 3. Armazena trechos de PDFs e seus embeddings para busca semântica.
-- O serviço de embeddings configura 768 dimensões para gemini-embedding-001.
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    content TEXT NOT NULL,
    -- Vetor de 768 dimensões gerado pelo serviço de embeddings.
    embedding VECTOR(768),
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Índices para localizar trechos de um documento.
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON public.document_chunks (document_id);

-- Índice HNSW para busca por similaridade de cosseno.
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
ON public.document_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 4. Função RPC de busca vetorial por distância de cosseno.
CREATE OR REPLACE FUNCTION match_document_chunks (
    query_embedding VECTOR(768),
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 5,
    filter_document_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    page_number INT,
    similarity FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.content,
        dc.page_number,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM public.document_chunks dc
    WHERE
        (filter_document_id IS NULL OR dc.document_id = filter_document_id)
        AND 1 - (dc.embedding <=> query_embedding) > match_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 5. Armazena sessões de conversa.
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT DEFAULT 'Nova Conversa',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Armazena mensagens e metadados de auditoria.
CREATE TABLE IF NOT EXISTS public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    -- Metadados técnicos, como SQL gerado ou trechos recuperados.
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON public.chat_messages (session_id, created_at ASC);

-- 7. Row Level Security (RLS)
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Não crie políticas públicas: o backend deve usar uma chave service_role protegida.
DROP POLICY IF EXISTS "Permitir operacoes totais em documentos" ON public.documents;
DROP POLICY IF EXISTS "Permitir operacoes totais em chunks" ON public.document_chunks;
DROP POLICY IF EXISTS "Permitir operacoes de chat" ON public.chat_sessions;
DROP POLICY IF EXISTS "Permitir operacoes de mensagens" ON public.chat_messages;
