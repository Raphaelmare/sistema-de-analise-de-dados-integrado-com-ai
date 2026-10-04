import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import UploadFile

from app.core.config import settings
from app.core.supabase_client import get_supabase_client
from app.models.document import (
    DocumentType,
    DocumentResponse,
)
from app.services.parsers.excel_parser import ExcelParser
from app.services.parsers.pdf_parser import PDFParser
from app.services.rag.supabase_vector_store import supabase_vector_store
from app.services.rag.tabular_engine import tabular_engine

logger = logging.getLogger(__name__)
MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024


class UploadTooLargeError(ValueError):
    pass


class DocumentStore:
    """
    Armazena arquivos localmente e coordena seu processamento e catalogação.

    Planilhas e CSV são registrados no DuckDB; PDFs são indexados no Supabase
    quando o serviço e as credenciais estão disponíveis.
    """

    def __init__(self):
        self._documents: Dict[str, DocumentResponse] = {}
        self._file_paths: Dict[str, Path] = {}

    def get_document_type(self, filename: str) -> DocumentType:
        suffix = Path(filename).suffix.lower()
        if suffix in [".xlsx", ".xls"]:
            return DocumentType.EXCEL
        elif suffix == ".csv":
            return DocumentType.CSV
        elif suffix == ".pdf":
            return DocumentType.PDF
        return DocumentType.UNSUPPORTED

    def rehydrate_from_storage(self) -> int:
        """
        Recarrega no DuckDB os arquivos tabulares encontrados no diretório de uploads.
        """
        if not settings.UPLOADS_DIR.exists():
            return 0

        rehydrated_count = 0
        for file_path in settings.UPLOADS_DIR.glob("*"):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            doc_type = self.get_document_type(file_path.name)
            if doc_type in (DocumentType.EXCEL, DocumentType.CSV):
                try:
                    tables = ExcelParser.load_dataframes(file_path)
                    for table_name, df in tables.items():
                        tabular_engine.register_dataframe(table_name, df)
                    rehydrated_count += 1
                    logger.info(f"[DocumentStore] Reidratado: {file_path.name} -> Tabelas: {list(tables.keys())}")
                except Exception as exc:
                    logger.error(f"[DocumentStore] Erro ao reidratar {file_path.name}: {exc}")

        return rehydrated_count

    async def save_and_process_upload(self, upload_file: UploadFile) -> DocumentResponse:
        """
        Salva e processa um arquivo de até 25 MiB.

        Planilhas e CSV são carregados no DuckDB. Para PDFs, tenta gerar embeddings
        e indexar os trechos no Supabase; os metadados do arquivo também são
        persistidos remotamente quando o cliente está configurado.
        """
        filename = upload_file.filename or "unnamed_file"
        doc_type = self.get_document_type(filename)

        if doc_type == DocumentType.UNSUPPORTED:
            raise ValueError(f"Extensao de arquivo nao suportada para analise: {filename}")

        file_id = str(uuid.uuid4())
        sanitized_filename = "".join(c for c in filename if c.isalnum() or c in (".", "_", "-")).strip()
        target_path = settings.UPLOADS_DIR / f"{file_id}_{sanitized_filename}"

        # Grava em blocos para aplicar o limite sem carregar o arquivo inteiro na memória.
        file_size = 0
        try:
            with open(target_path, "wb") as buffer:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > MAX_UPLOAD_SIZE_BYTES:
                        raise UploadTooLargeError("Cada arquivo pode ter no maximo 25 MiB.")
                    buffer.write(chunk)
        except Exception:
            target_path.unlink(missing_ok=True)
            raise

        # Extrai metadados e encaminha o conteúdo ao mecanismo correspondente.
        metadata_dict = {}

        if doc_type in (DocumentType.EXCEL, DocumentType.CSV):
            metadata = ExcelParser.extract_metadata(target_path)
            metadata_dict = metadata.model_dump()

            # Registra cada aba ou arquivo como tabela analítica no DuckDB.
            tables = ExcelParser.load_dataframes(target_path)
            for table_name, df in tables.items():
                tabular_engine.register_dataframe(table_name, df)

        elif doc_type == DocumentType.PDF:
            metadata = PDFParser.extract_metadata(target_path)
            metadata_dict = metadata.model_dump()

            # Divide o texto por página e indexa seus vetores no Supabase.
            pages_data = PDFParser.parse_pages(target_path)
            try:
                supabase_vector_store.index_document_chunks(file_id, pages_data)
            except Exception as e:
                logger.error(f"Erro ao indexar chunks no Supabase: {e}")

        else:
            metadata = {}

        # Persiste os metadados no Supabase quando o cliente está configurado.
        supabase = get_supabase_client()
        if supabase:
            try:
                supabase.table("documents").insert({
                    "id": file_id,
                    "filename": filename,
                    "file_type": doc_type.value,
                    "file_size_bytes": file_size,
                    "storage_path": str(target_path),
                    "metadata": metadata_dict,
                }).execute()
            except Exception as exc:
                logger.error(f"[DocumentStore] Falha ao registrar documento no Supabase: {exc}")

        doc_response = DocumentResponse(
            file_id=file_id,
            filename=filename,
            file_type=doc_type,
            file_size_bytes=file_size,
            uploaded_at=datetime.now(timezone.utc),
            metadata=metadata,
        )

        self._documents[file_id] = doc_response
        self._file_paths[file_id] = target_path

        return doc_response

    def list_documents(self) -> List[DocumentResponse]:
        """
        Retorna o catálogo do Supabase quando disponível; caso contrário, usa o cache local.
        """
        supabase = get_supabase_client()
        if supabase:
            try:
                res = supabase.table("documents").select("*").order("created_at", desc=True).execute()
                if res.data:
                    results = []
                    for row in res.data:
                        results.append(
                            DocumentResponse(
                                file_id=row["id"],
                                filename=row["filename"],
                                file_type=DocumentType(row["file_type"]),
                                file_size_bytes=row["file_size_bytes"],
                                uploaded_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                                metadata=row.get("metadata", {}),
                            )
                        )
                    return results
            except Exception as exc:
                logger.warning(f"[DocumentStore] Falha ao listar do Supabase, usando cache local: {exc}")

        return list(self._documents.values())

    def get_document(self, file_id: str) -> Optional[DocumentResponse]:
        return self._documents.get(file_id)

    def get_file_path(self, file_id: str) -> Optional[Path]:
        return self._file_paths.get(file_id)


document_store = DocumentStore()
