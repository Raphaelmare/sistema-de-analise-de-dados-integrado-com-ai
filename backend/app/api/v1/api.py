from fastapi import APIRouter
from app.api.v1.endpoints import upload, chat

api_router = APIRouter()
api_router.include_router(upload.router, tags=["Documentos e Ingestao"])
api_router.include_router(chat.router, tags=["Conversacao e Analise"])
