import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.supabase_client import get_supabase_client
from app.services.agent.gemini_agent import gemini_agent

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Pergunta ou instrucao em linguagem natural")
    session_id: Optional[str] = Field(None, description="Identificador unico da sessao de conversacao")


class SessionResponse(BaseModel):
    session_id: str
    title: str


@router.post(
    "/chat",
    summary="Envia uma pergunta ao agente e recebe a resposta em tempo real via streaming SSE",
)
async def chat_stream(request: ChatRequest):
    """
    Encaminha a pergunta ao agente e transmite eventos SSE ao cliente.
    """
    session_id = request.session_id
    supabase = get_supabase_client()

    # Cria um identificador de sessão e tenta persistir a sessão no Supabase.
    if not session_id and supabase:
        try:
            new_id = str(uuid.uuid4())
            supabase.table("chat_sessions").insert({
                "id": new_id,
                "title": request.message[:40] + ("..." if len(request.message) > 40 else ""),
            }).execute()
            session_id = new_id
        except Exception:
            session_id = str(uuid.uuid4())
    elif not session_id:
        session_id = str(uuid.uuid4())

    return StreamingResponse(
        gemini_agent.stream_chat(request.message, session_id=session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post(
    "/chat/session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inicializa uma nova sessao de chat",
)
async def create_chat_session(title: Optional[str] = "Nova Analise"):
    """
    Cria um identificador de sessão e, se disponível, persiste-o no Supabase.
    """
    session_id = str(uuid.uuid4())
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("chat_sessions").insert({
                "id": session_id,
                "title": title or "Nova Analise",
            }).execute()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao criar sessao no banco: {exc}")

    return SessionResponse(session_id=session_id, title=title or "Nova Analise")


@router.get(
    "/chat/session/{session_id}/messages",
    summary="Recupera o historico de mensagens de uma sessao",
)
async def get_session_messages(session_id: str):
    """
    Retorna as mensagens persistidas para a sessão informada.
    """
    supabase = get_supabase_client()
    if not supabase:
        return []

    try:
        response = (
            supabase.table("chat_messages")
            .select("id, role, content, metadata, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao recuperar mensagens: {exc}")
