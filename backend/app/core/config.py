from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações da aplicação e das integrações externas.
    """
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000

    # Configurações reservadas; o agente atual usa somente o Google Gemini.
    AI_PROVIDER: str = "gemini"

    # Google Gemini, usado pelo agente e pelo serviço de embeddings.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Configurações da Groq reservadas para uma integração futura.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Supabase (PostgreSQL e pgvector).
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # Diretórios locais para arquivos enviados e armazenamento auxiliar.
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOADS_DIR: Path = DATA_DIR / "uploads"
    CHROMA_PERSIST_DIR: Path = DATA_DIR / "vector_db"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Garante que os diretórios locais existam antes de iniciar a aplicação.
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
