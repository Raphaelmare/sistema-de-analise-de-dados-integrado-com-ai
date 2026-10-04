import logging
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.models.document import DocumentResponse
from app.services.document_store import UploadTooLargeError, document_store

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_FILES_PER_UPLOAD = 10


@router.post(
    "/upload",
    response_model=List[DocumentResponse],
    summary="Recebe e processa documentos Excel, CSV ou PDF",
    status_code=status.HTTP_201_CREATED,
)
async def upload_documents(
    files: List[UploadFile] = File(..., description="Arquivos para análise (.xlsx, .xls, .csv ou .pdf)"),
):
    """
    Valida a quantidade e o tipo dos arquivos, aplica os limites de tamanho e os processa.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum arquivo enviado para processamento.",
        )

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Envie no maximo {MAX_FILES_PER_UPLOAD} arquivos por requisicao.",
        )

    processed_documents: List[DocumentResponse] = []

    for file in files:
        try:
            doc_response = await document_store.save_and_process_upload(file)
            processed_documents.append(doc_response)
        except UploadTooLargeError as size_err:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=str(size_err),
            )
        except ValueError as val_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(val_err),
            )
        except Exception as err:
            logger.exception("Falha ao processar upload de arquivo.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha no processamento do arquivo enviado.",
            ) from err

    return processed_documents


@router.get(
    "/documents",
    response_model=List[DocumentResponse],
    summary="Lista os documentos disponíveis para consulta",
)
async def list_documents():
    """
    Retorna os documentos conhecidos pela aplicação e seus metadados.
    """
    return document_store.list_documents()
