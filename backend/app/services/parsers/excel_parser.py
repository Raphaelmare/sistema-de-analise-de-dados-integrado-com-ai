import re
import unicodedata
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

from app.models.document import (
    ColumnMetadata,
    SheetMetadata,
    TabularMetadata,
    DocumentType,
)


def normalize_identifier(text: str) -> str:
    """
    Remove acentos, caracteres especiais e espaços e converte o texto para snake_case.
    Exemplo: 'Salario Base (R$)' -> 'salario_base_r'
             'Avaliacao do Funcionario' -> 'avaliacao_do_funcionario'
    """
    if not text:
        return "coluna"
    nfkd = unicodedata.normalize("NFKD", str(text))
    ascii_text = nfkd.encode("ASCII", "ignore").decode("ASCII")
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_text).lower().strip("_")
    clean = re.sub(r"_+", "_", clean)
    return clean or "coluna"


class ExcelParser:
    """
    Lê arquivos Excel e CSV e normaliza seus nomes para uso como identificadores SQL.
    """

    @staticmethod
    def detect_type(file_path: Path) -> DocumentType:
        suffix = file_path.suffix.lower()
        if suffix in [".xlsx", ".xls"]:
            return DocumentType.EXCEL
        elif suffix == ".csv":
            return DocumentType.CSV
        return DocumentType.UNSUPPORTED

    @classmethod
    def get_clean_table_base_name(cls, file_path: Path) -> str:
        """
        Extrai o nome-base do arquivo e remove um prefixo UUID, se presente.
        Ex: 'd89871e6-d328-4d62-a26b-c36bcd63f93b_BaseFuncionarios.xlsx' -> 'basefuncionarios'
        """
        stem = file_path.stem
        # Remove um UUID de 36 caracteres seguido por sublinhado.
        stem = re.sub(r"^[a-f0-9\-]{36}_", "", stem, flags=re.IGNORECASE)
        return normalize_identifier(stem)

    @classmethod
    def load_dataframes(cls, file_path: Path) -> Dict[str, pd.DataFrame]:
        """
        Carrega cada CSV ou aba de Excel em um DataFrame com colunas normalizadas.
        """
        doc_type = cls.detect_type(file_path)
        base_name = cls.get_clean_table_base_name(file_path)

        if doc_type == DocumentType.CSV:
            try:
                df = pd.read_csv(file_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="latin-1")

            # Normaliza os nomes das colunas para uso em SQL.
            df.columns = [normalize_identifier(c) for c in df.columns]
            return {base_name: df}

        elif doc_type == DocumentType.EXCEL:
            excel_file = pd.ExcelFile(file_path)
            sheets_data = {}
            sheet_names = excel_file.sheet_names

            for sheet_name in sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                # Normaliza os nomes das colunas para uso em SQL.
                df.columns = [normalize_identifier(c) for c in df.columns]

                norm_sheet = normalize_identifier(sheet_name)
                is_generic_sheet = norm_sheet in ("plan1", "planilha1", "sheet1", "tabela1", "dados")

                # Usa o nome do arquivo para abas genéricas ou arquivos com uma única aba.
                if is_generic_sheet or len(sheet_names) == 1:
                    clean_table_name = base_name
                else:
                    clean_table_name = f"{base_name}_{norm_sheet}"

                sheets_data[clean_table_name] = df

            return sheets_data

        else:
            raise ValueError(f"Formato de arquivo tabular nao suportado: {file_path.suffix}")

    @classmethod
    def extract_metadata(cls, file_path: Path) -> TabularMetadata:
        """
        Gera metadados das tabelas e colunas para orientar a geração de SQL.
        """
        tables = cls.load_dataframes(file_path)
        sheets_metadata: List[SheetMetadata] = []
        summary_lines: List[str] = []

        for table_name, df in tables.items():
            row_count, col_count = df.shape
            columns_meta: List[ColumnMetadata] = []

            for col in df.columns:
                series = df[col]
                non_null = int(series.count())
                null_count = int(series.isna().sum())

                sample_vals = series.dropna().drop_duplicates().head(3).tolist()
                sanitized_samples = [
                    str(v) if not isinstance(v, (int, float, bool, str)) else v
                    for v in sample_vals
                ]

                columns_meta.append(
                    ColumnMetadata(
                        name=str(col),
                        data_type=str(series.dtype),
                        non_null_count=non_null,
                        null_count=null_count,
                        sample_values=sanitized_samples,
                    )
                )

            sheet_meta = SheetMetadata(
                sheet_name=table_name,
                row_count=row_count,
                column_count=col_count,
                columns=columns_meta,
            )
            sheets_metadata.append(sheet_meta)

            cols_desc = ", ".join([f"{c.name} ({c.data_type})" for c in columns_meta])
            summary_lines.append(
                f"Tabela `{table_name}`: {row_count} registros, {col_count} colunas. Colunas: [{cols_desc}]"
            )

        return TabularMetadata(
            sheets=sheets_metadata,
            summary_description="\n".join(summary_lines),
        )
