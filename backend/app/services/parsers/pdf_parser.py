from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

from app.models.document import (
    TextPageMetadata,
    TextDocumentMetadata,
)


class PDFParser:
    """
    Extrai texto e metadados de PDFs, preservando a numeração das páginas.
    """

    @classmethod
    def parse_pages(cls, file_path: Path) -> List[Dict[str, Any]]:
        """
        Extrai o texto de cada página separadamente.
        """
        reader = PdfReader(str(file_path))
        pages_content: List[Dict[str, Any]] = []

        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            # Remove linhas vazias e espaços no início e no fim de cada linha.
            clean_text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
            pages_content.append({
                "page_number": idx + 1,
                "text": clean_text,
                "character_count": len(clean_text),
            })

        return pages_content

    @classmethod
    def extract_metadata(cls, file_path: Path) -> TextDocumentMetadata:
        """
        Gera metadados com a contagem de páginas e caracteres e uma prévia do texto.
        """
        pages_data = cls.parse_pages(file_path)
        total_pages = len(pages_data)
        total_characters = sum(p["character_count"] for p in pages_data)

        pages_meta = [
            TextPageMetadata(
                page_number=p["page_number"],
                character_count=p["character_count"],
                preview=(p["text"][:200] + "...") if len(p["text"]) > 200 else p["text"],
            )
            for p in pages_data
        ]

        return TextDocumentMetadata(
            total_pages=total_pages,
            total_characters=total_characters,
            pages=pages_meta,
        )
