import re
import logging
from typing import Dict, Any, List, Optional
import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class TabularEngine:
    """
    Executa consultas SQL somente de leitura sobre tabelas em memória no DuckDB.

    O acesso a arquivos externos é desativado na conexão. Consultas sem LIMIT
    explícito recebem um limite padrão de linhas retornadas.
    """

    def __init__(self):
        # Mantém os dados em memória e bloqueia operações sobre arquivos externos.
        self._conn = duckdb.connect(database=":memory:")
        self._conn.execute("SET enable_external_access = false")
        self._registered_tables: Dict[str, Dict[str, Any]] = {}

    def register_dataframe(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Registra um DataFrame como tabela consultável no DuckDB.
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", table_name).lower().strip("_")
        if not clean_name:
            clean_name = "tabela_dados"

        self._conn.register(clean_name, df)
        self._registered_tables[clean_name] = {
            "row_count": len(df),
            "columns": [{"name": str(col), "type": str(df[col].dtype)} for col in df.columns],
        }
        logger.info(f"[TabularEngine] Tabela '{clean_name}' registrada com {len(df)} linhas.")

    def get_registered_tables(self) -> List[str]:
        return list(self._registered_tables.keys())

    def get_schema_context_prompt(self) -> str:
        """
        Descreve as tabelas e colunas carregadas para compor o contexto do Gemini.
        """
        if not self._registered_tables:
            return "Nenhuma tabela analitica carregada no momento."

        lines = ["Tabelas disponiveis no motor analitico (DuckDB SQL):"]
        for table, meta in self._registered_tables.items():
            cols = ", ".join([f"{c['name']} ({c['type']})" for c in meta["columns"]])
            lines.append(f"- Tabela `{table}` ({meta['row_count']} registros): colunas [{cols}]")

        return "\n".join(lines)

    def execute_query(self, sql_query: str, max_rows: int = 50) -> Dict[str, Any]:
        """
        Executa uma instrução de leitura e retorna linhas e uma tabela Markdown.
        """
        cleaned_sql = sql_query.strip().rstrip(";")
        if len(self._conn.extract_statements(cleaned_sql)) != 1:
            raise ValueError("Apenas uma consulta SQL por vez e permitida.")

        # Aceita apenas os comandos de leitura previstos pelo motor.
        blocked_keywords = ["drop", "delete", "update", "insert", "alter", "create", "truncate", "grant", "revoke"]
        first_token = cleaned_sql.split()[0].lower() if cleaned_sql.split() else ""

        if first_token not in ("select", "with", "describe", "explain", "show"):
            raise ValueError(f"Operacao nao autorizada. Apenas consultas de leitura sao permitidas. Recebido: {first_token}")

        for kw in blocked_keywords:
            # Bloqueia palavras de operações de escrita ou alteração estrutural.
            if re.search(rf"\b{kw}\b", cleaned_sql, re.IGNORECASE):
                raise ValueError(f"Operacao de escrita ou modificacao estrutural bloqueada: {kw}")

        # Aplica o limite padrão somente quando a consulta não especifica LIMIT.
        if not re.search(r"\blimit\s+\d+", cleaned_sql, re.IGNORECASE):
            execution_sql = f"{cleaned_sql} LIMIT {max_rows}"
        else:
            execution_sql = cleaned_sql

        try:
            result_df: pd.DataFrame = self._conn.execute(execution_sql).df()

            columns = list(result_df.columns)
            records = result_df.to_dict(orient="records")

            # Formata os resultados em Markdown sem dependência adicional.
            if result_df.empty:
                markdown_table = "Nenhum resultado retornado."
            else:
                header = "| " + " | ".join(str(c) for c in columns) + " |"
                sep = "| " + " | ".join(["---"] * len(columns)) + " |"
                data_rows = [
                    "| " + " | ".join(str(row.get(c, "")) for c in columns) + " |"
                    for row in records
                ]
                markdown_table = "\n".join([header, sep] + data_rows)

            return {
                "success": True,
                "executed_sql": execution_sql,
                "row_count": len(result_df),
                "columns": columns,
                "rows": records,
                "markdown_table": markdown_table,
            }
        except Exception as exc:
            logger.error(f"[TabularEngine] Erro na execucao SQL: {exc}")
            return {
                "success": False,
                "executed_sql": execution_sql if "execution_sql" in locals() else cleaned_sql,
                "error": str(exc),
                "row_count": 0,
                "columns": [],
                "rows": [],
                "markdown_table": f"Erro na execucao SQL: {str(exc)}",
            }


tabular_engine = TabularEngine()
