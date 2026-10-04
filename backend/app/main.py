from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.api.v1.api import api_router
from app.services.document_store import document_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação e carrega planilhas locais no DuckDB.
    """
    rehydrated = document_store.rehydrate_from_storage()
    print(f"[Lifespan] Inicialização concluída. {rehydrated} arquivo(s) tabular(es) carregado(s) no DuckDB.")
    yield


app = FastAPI(
    title="Enterprise Document & Data Assistant API",
    description="API local para análise de planilhas e busca em PDFs com Gemini, DuckDB e Supabase pgvector.",
    version="1.0.0",
    lifespan=lifespan,
)

# A aplicação é local; rejeita hosts e origens não autorizados.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "testserver"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Registra as rotas da API.
app.include_router(api_router, prefix="/api/v1")

# Define os diretórios de arquivos estáticos e do template da interface.
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", tags=["Interface Web"])
async def serve_index():
    """
    Entrega a página principal da interface web.
    """
    index_file = TEMPLATES_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "message": "Enterprise Document & Data Assistant API operante.",
        "documentation": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health", tags=["Healthcheck"])
async def health_check():
    """
    Retorna o estado da API, o modelo Gemini configurado e as tabelas carregadas.
    """
    from app.services.rag.tabular_engine import tabular_engine

    return {
        "status": "operational",
        "gemini_model": settings.GEMINI_MODEL,
        "environment": settings.APP_ENV,
        "active_tables": tabular_engine.get_registered_tables(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
