from enum import Enum
from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, Field
from datetime import datetime


class DocumentType(str, Enum):
    EXCEL = "excel"
    CSV = "csv"
    PDF = "pdf"
    UNSUPPORTED = "unsupported"


class ColumnMetadata(BaseModel):
    name: str
    data_type: str
    non_null_count: int
    null_count: int
    sample_values: List[Any] = Field(default_factory=list)


class SheetMetadata(BaseModel):
    sheet_name: str
    row_count: int
    column_count: int
    columns: List[ColumnMetadata]


class TabularMetadata(BaseModel):
    sheets: List[SheetMetadata]
    summary_description: str


class TextPageMetadata(BaseModel):
    page_number: int
    character_count: int
    preview: str


class TextDocumentMetadata(BaseModel):
    total_pages: int
    total_characters: int
    pages: List[TextPageMetadata] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    file_id: str
    filename: str
    file_type: DocumentType
    file_size_bytes: int
    uploaded_at: datetime
    metadata: Union[TabularMetadata, TextDocumentMetadata, Dict[str, Any]]
