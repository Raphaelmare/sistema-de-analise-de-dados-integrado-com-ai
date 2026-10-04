import re
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.supabase_client import get_supabase_client
from app.services.rag.tabular_engine import tabular_engine
from app.services.rag.supabase_vector_store import supabase_vector_store
from app.services.agent.prompts import (
    ROUTER_SYSTEM_PROMPT,
    TEXT_TO_SQL_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class GeminiAgent:
    """
    Orquestra classificação de perguntas, geração de SQL e busca vetorial com Gemini.

    O DuckDB executa as consultas tabulares; as respostas são transmitidas por SSE.
    """

    def __init__(self):
        self.model_name = settings.GEMINI_MODEL
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY não configurada no arquivo de ambiente.")
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def classify_intent(self, query: str) -> str:
        """
        Classifica a pergunta como TABULAR, DOCUMENTAL ou GERAL.
        """
        client = self._get_client()
        schema_context = tabular_engine.get_schema_context_prompt()
        prompt = f"{ROUTER_SYSTEM_PROMPT.format(data_context=schema_context)}\n\nConsulta do usuario: \"{query}\"\nClassificacao:"

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    temperature=0.0,
                    max_output_tokens=100,
                )
            )
            raw_text = response.text or ""
            intent = raw_text.strip().upper()
            if "TABULAR" in intent:
                return "TABULAR"
            elif "DOCUMENTAL" in intent:
                return "DOCUMENTAL"
            return "GERAL"
        except Exception as exc:
            logger.error(f"[GeminiAgent] Erro na classificacao de intencao: {exc}")
            tables = tabular_engine.get_registered_tables()
            if tables:
                return "TABULAR"
            return "DOCUMENTAL"

    def generate_sql(self, query: str) -> str:
        """
        Converte a pergunta em uma consulta SQL destinada ao DuckDB.
        """
        client = self._get_client()
        schema_context = tabular_engine.get_schema_context_prompt()
        prompt = f"{TEXT_TO_SQL_SYSTEM_PROMPT.format(schema_context=schema_context)}\n\nPergunta do usuario: {query}\nSQL:"

        response = client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                temperature=0.0,
                max_output_tokens=400,
            )
        )
        raw_sql = response.text or ""
        clean_sql = re.sub(r"^```(?:sql)?\s*", "", raw_sql.strip(), flags=re.IGNORECASE)
        clean_sql = re.sub(r"\s*```$", "", clean_sql)
        return clean_sql.strip()

    async def stream_chat(
        self,
        query: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Processa a pergunta e transmite eventos SSE com status, conteúdo e metadados.
        """
        client = self._get_client()
        full_response_text = ""
        metadata: Dict[str, Any] = {"intent": "GERAL"}

        # Classifica a pergunta para selecionar o mecanismo de consulta.
        yield f"data: {json.dumps({'type': 'status', 'message': 'Analisando intencao da consulta...'})}\n\n"
        intent = self.classify_intent(query)
        metadata["intent"] = intent

        context_text = ""

        # Consulta o DuckDB, a busca vetorial ou prepara uma resposta geral.
        if intent == "TABULAR":
            yield f"data: {json.dumps({'type': 'status', 'message': 'Contexto tabular identificado. Construindo consulta analitica...'})}\n\n"
            try:
                sql_query = self.generate_sql(query)
                metadata["sql_query"] = sql_query
                yield f"data: {json.dumps({'type': 'sql', 'query': sql_query})}\n\n"

                yield f"data: {json.dumps({'type': 'status', 'message': 'Executando calculo analitico no DuckDB...'})}\n\n"
                query_result = tabular_engine.execute_query(sql_query)
                metadata["sql_result"] = {
                    "success": query_result["success"],
                    "row_count": query_result["row_count"],
                }

                if query_result["success"]:
                    context_text = (
                        f"Instrucao SQL Executada:\n{query_result['executed_sql']}\n\n"
                        f"Tabela de Resultados do DuckDB:\n{query_result['markdown_table']}\n\n"
                        f"Amostra dos registros (JSON):\n{json.dumps(query_result['rows'][:10], ensure_ascii=False)}"
                    )
                else:
                    context_text = f"Erro na execucao da consulta SQL: {query_result.get('error')}"

            except Exception as e:
                logger.error(f"[GeminiAgent] Erro no fluxo Tabular: {e}")
                context_text = f"Nao foi possivel executar a consulta SQL: {str(e)}"

        elif intent == "DOCUMENTAL":
            yield f"data: {json.dumps({'type': 'status', 'message': 'Consultando base de conhecimento vetorial no Supabase...'})}\n\n"
            try:
                chunks = supabase_vector_store.search_similar_chunks(query, match_count=4)
                metadata["chunks_found"] = len(chunks)

                if chunks:
                    formatted_chunks = []
                    for c in chunks:
                        formatted_chunks.append(
                            f"[Documento {c.get('document_id', '')} - Pagina {c.get('page_number', 'N/D')}]\n{c.get('content', '')}"
                        )
                    context_text = "Trechos recuperados dos documentos PDF:\n" + "\n---\n".join(formatted_chunks)
                else:
                    context_text = "Nenhum trecho com similaridade suficiente foi localizado na base vetorial."
            except Exception as e:
                logger.error(f"[GeminiAgent] Erro no fluxo Documental: {e}")
                context_text = f"Falha na consulta vetorial: {str(e)}"

        else:
            context_text = "Consulta geral ou de navegacao no assistente."

        # Gera e transmite a síntese final.
        yield f"data: {json.dumps({'type': 'status', 'message': 'Sintetizando resposta corporativa...'})}\n\n"

        synthesis_prompt = (
            f"{SYNTHESIS_SYSTEM_PROMPT}\n\n"
            f"Contexto dos dados extraidos:\n{context_text}\n\n"
            f"Pergunta original do usuario: {query}\n\n"
            f"Resposta analitica estruturada:"
        )

        try:
            response_stream = client.models.generate_content_stream(
                model=self.model_name,
                contents=synthesis_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                )
            )

            for chunk in response_stream:
                token = chunk.text or ""
                if token:
                    full_response_text += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        except Exception as stream_err:
            logger.error(f"[GeminiAgent] Erro no streaming de sintese: {stream_err}")
            err_msg = f"\n\n[Aviso]: Interrupcao na transmissao do modelo: {str(stream_err)}"
            full_response_text += err_msg
            yield f"data: {json.dumps({'type': 'token', 'content': err_msg})}\n\n"

        # Persiste a pergunta e a resposta quando o Supabase está disponível.
        supabase = get_supabase_client()
        if supabase and session_id:
            try:
                # Garante a existência da sessão antes de inserir mensagens relacionadas.
                supabase.table("chat_sessions").upsert({
                    "id": session_id,
                    "title": query[:40] + ("..." if len(query) > 40 else ""),
                }).execute()

                # Registra a pergunta do usuário.
                supabase.table("chat_messages").insert({
                    "session_id": session_id,
                    "role": "user",
                    "content": query,
                    "metadata": {},
                }).execute()

                # Registra a resposta e os metadados técnicos da consulta.
                supabase.table("chat_messages").insert({
                    "session_id": session_id,
                    "role": "assistant",
                    "content": full_response_text,
                    "metadata": metadata,
                }).execute()
            except Exception as hist_err:
                logger.warning(f"[GeminiAgent] Falha ao gravar historico no Supabase: {hist_err}")

        # Sinaliza o término do fluxo SSE.
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'metadata': metadata})}\n\n"


gemini_agent = GeminiAgent()
