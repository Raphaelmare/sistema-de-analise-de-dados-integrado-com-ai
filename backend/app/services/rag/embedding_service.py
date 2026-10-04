import logging
from typing import List
import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Gera embeddings de 768 dimensões com o modelo Gemini configurado no serviço.
    """

    def __init__(self):
        self.model_name = "gemini-embedding-001"
        self.dimension = 768
        self._client = None

    def _get_client(self):
        if self._client is None and settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                logger.warning(f"Nao foi possivel inicializar o cliente Google GenAI: {e}")
                self._client = None
        return self._client

    def generate_embedding(self, text: str) -> List[float]:
        """
        Gera o embedding de um texto ou um vetor pseudoaleatório de contingência.

        O vetor de contingência permite executar fluxos locais sem credenciais,
        mas não representa o significado do texto e não serve para busca semântica.
        """
        client = self._get_client()

        if client and settings.GEMINI_API_KEY:
            try:
                from google.genai import types
                response = client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=self.dimension)
                )
                if hasattr(response, "embedding") and hasattr(response.embedding, "values"):
                    return [float(v) for v in response.embedding.values]
                elif hasattr(response, "embeddings") and len(response.embeddings) > 0:
                    return [float(v) for v in response.embeddings[0].values]
            except Exception as exc:
                logger.error(f"Erro ao invocar API de Embeddings do Gemini: {exc}")
                pass

        # O fallback normalizado serve apenas para testes sem acesso à API.
        seed = abs(hash(text)) % (2**32)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self.dimension)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return [float(v) for v in vec]

    def generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Gera embeddings individualmente para uma lista de textos.
        """
        return [self.generate_embedding(t) for t in texts]


embedding_service = EmbeddingService()
