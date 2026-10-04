import logging
from typing import List, Dict, Any, Optional
from app.core.supabase_client import get_supabase_client
from app.services.rag.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class SupabaseVectorStore:
    """
    Divide, indexa e pesquisa trechos de documentos no Supabase com pgvector.
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document_pages(self, pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Divide o texto de cada página em trechos sobrepostos e preserva sua origem.
        """
        chunks: List[Dict[str, Any]] = []
        global_chunk_idx = 0

        for page_info in pages_data:
            page_num = page_info["page_number"]
            page_text = page_info["text"]

            if not page_text.strip():
                continue

            # Mantém em um único trecho o texto que cabe no limite configurado.
            if len(page_text) <= self.chunk_size:
                chunks.append({
                    "chunk_index": global_chunk_idx,
                    "page_number": page_num,
                    "content": page_text,
                })
                global_chunk_idx += 1
                continue

            # Avança pelo texto mantendo a sobreposição configurada.
            start = 0
            while start < len(page_text):
                end = start + self.chunk_size
                chunk_slice = page_text[start:end].strip()

                if chunk_slice:
                    chunks.append({
                        "chunk_index": global_chunk_idx,
                        "page_number": page_num,
                        "content": chunk_slice,
                    })
                    global_chunk_idx += 1

                start += self.chunk_size - self.chunk_overlap

        return chunks

    def index_document_chunks(self, document_id: str, pages_data: List[Dict[str, Any]]) -> int:
        """
        Gera os embeddings dos trechos e os grava em lotes no Supabase.
        """
        client = get_supabase_client()
        if not client:
            logger.warning("[SupabaseVectorStore] Cliente Supabase nao configurado. Pulando persistencia remota.")
            return 0

        chunks = self.chunk_document_pages(pages_data)
        if not chunks:
            return 0

        # Prepara os registros antes de enviá-los ao banco.
        records = []
        for ch in chunks:
            vector = embedding_service.generate_embedding(ch["content"])
            records.append({
                "document_id": document_id,
                "chunk_index": ch["chunk_index"],
                "page_number": ch["page_number"],
                "content": ch["content"],
                "embedding": vector,
            })

        try:
            # Divide a inserção em lotes de até 50 registros.
            batch_size = 50
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                client.table("document_chunks").insert(batch).execute()

            logger.info(f"[SupabaseVectorStore] {len(records)} chunks indexados para o documento {document_id}")
            return len(records)
        except Exception as exc:
            logger.error(f"[SupabaseVectorStore] Erro ao gravar chunks no Supabase: {exc}")
            raise exc

    def search_similar_chunks(
        self,
        query: str,
        match_count: int = 5,
        match_threshold: float = 0.3,
        filter_document_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Busca trechos por similaridade de cosseno usando a função RPC do Supabase.
        """
        client = get_supabase_client()
        if not client:
            logger.warning("[SupabaseVectorStore] Cliente Supabase nao configurado. Nao foi possivel buscar.")
            return []

        query_vector = embedding_service.generate_embedding(query)

        rpc_params = {
            "query_embedding": query_vector,
            "match_threshold": match_threshold,
            "match_count": match_count,
        }
        if filter_document_id:
            rpc_params["filter_document_id"] = filter_document_id

        try:
            response = client.rpc("match_document_chunks", rpc_params).execute()
            return response.data or []
        except Exception as exc:
            logger.error(f"[SupabaseVectorStore] Erro na chamada RPC match_document_chunks: {exc}")
            return []


supabase_vector_store = SupabaseVectorStore()
