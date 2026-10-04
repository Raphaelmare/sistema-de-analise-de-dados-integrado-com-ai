# Enterprise Document & Data Assistant

Aplicação web local para consultar planilhas e documentos PDF em linguagem natural. O backend usa FastAPI, Google Gemini, DuckDB e, opcionalmente, Supabase com pgvector.

## Recursos

- **Planilhas Excel e arquivos CSV:** leitura com pandas e registro das tabelas no DuckDB em memória. O Gemini classifica a pergunta e gera SQL; o DuckDB executa a consulta sobre as tabelas carregadas.
- **Documentos PDF:** extração de texto por página, divisão em trechos e busca vetorial no Supabase com embeddings `gemini-embedding-001` de 768 dimensões.
- **Chat:** respostas transmitidas por Server-Sent Events (SSE), com exibição da consulta SQL gerada e exportação da conversa para Markdown.
- **Interface:** HTML, CSS e JavaScript servidos pelo FastAPI. Tailwind CSS e Marked.js são carregados de CDNs; é necessária conexão com a internet para esses recursos.

Os cálculos SQL são executados pelo DuckDB, mas a classificação, a geração de SQL e a síntese textual dependem de um modelo de linguagem e devem ser conferidas. O sistema não garante respostas infalíveis.

## Componentes

```text
.
├── README.md
├── .gitignore
└── backend/
    ├── .env.example
    ├── requirements.txt
    ├── supabase_schema.sql
    └── app/
        ├── main.py
        ├── api/v1/
        │   ├── api.py
        │   └── endpoints/
        │       ├── chat.py
        │       └── upload.py
        ├── core/
        │   ├── config.py
        │   └── supabase_client.py
        ├── models/document.py
        ├── services/
        │   ├── agent/
        │   ├── parsers/
        │   ├── rag/
        │   └── document_store.py
        ├── static/
        │   ├── css/style.css
        │   └── js/app.js
        └── templates/index.html
```

Arquivos enviados e índices locais são armazenados em `backend/data/`. O diretório do ambiente virtual, arquivos `.env`, dados de teste e scripts de teste locais são ignorados pelo Git.

## Requisitos

- Python 3.10 ou superior.
- Uma chave da API Google Gemini para classificação, geração de SQL, síntese e embeddings.
- Um projeto Supabase com pgvector para busca de PDFs e persistência do histórico. A aplicação pode iniciar sem Supabase, mas as funções que dependem dele não estarão disponíveis.
- Conexão com a internet para acessar o Gemini, o Supabase e os recursos de interface carregados por CDN.

## Configuração no Windows

Abra o PowerShell na raiz do projeto:

```powershell
Set-Location backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `backend/.env` e informe as credenciais:

```dotenv
GEMINI_API_KEY="sua_chave_gemini"
GEMINI_MODEL="gemini-2.5-flash"
SUPABASE_URL="https://seu-projeto.supabase.co"
SUPABASE_KEY="sua_chave_service_role"
APP_HOST="127.0.0.1"
APP_PORT=8000
```

No painel SQL do Supabase, execute `backend/supabase_schema.sql` para criar as tabelas, a função de busca e os índices necessários. O schema habilita RLS e remove as políticas permissivas conhecidas; ele não cria políticas para acesso anônimo ou autenticado.

Inicie o servidor, ainda na pasta `backend`:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Acesse:

- Interface: <http://127.0.0.1:8000>
- Documentação da API: <http://127.0.0.1:8000/docs>
- Verificação de saúde: <http://127.0.0.1:8000/api/v1/health>

## Segurança e limites de uso

- Esta versão foi preparada para **uma pessoa por instalação, em uso local**. O servidor escuta em `127.0.0.1`; não o exponha a uma rede ou à internet. Os endpoints não implementam autenticação de usuários.
- Hosts HTTP e origens CORS são restritos a `localhost` e `127.0.0.1`.
- Cada envio aceita até 10 arquivos, com limite de 25 MiB por arquivo.
- O DuckDB é configurado sem acesso a arquivos externos e rejeita múltiplas instruções SQL na mesma consulta.
- Use uma chave Supabase `service_role` apenas no arquivo local `backend/.env`. Essa chave ignora RLS e nunca deve ser enviada ao navegador nem incluída no Git.
- Não publique arquivos `.env`, documentos enviados ou dados reais. As regras do `.gitignore` excluem esses itens e os scripts `test*.py`.

## Testes locais

Os scripts de teste estão excluídos do Git, mas podem ser executados no diretório local do projeto. Na pasta `backend`:

```powershell
python -m unittest test_security_controls
python test_phase5.py
```

`test_phase3.py`, `test_phase4.py` e `test_supabase_connection.py` podem chamar APIs externas ou gravar no Supabase. Execute-os apenas com credenciais e dados de teste.

## API principal

- `POST /api/v1/upload`: recebe arquivos Excel, CSV ou PDF.
- `GET /api/v1/documents`: lista os documentos conhecidos pela aplicação.
- `POST /api/v1/chat/session`: cria uma sessão de conversa.
- `POST /api/v1/chat`: envia uma pergunta e retorna eventos SSE.
- `GET /api/v1/chat/session/{session_id}/messages`: recupera mensagens persistidas para a sessão.

## Limitações conhecidas

- Consultas tabulares são mantidas em memória e reconstruídas a partir dos arquivos locais ao iniciar o servidor.
- A busca vetorial e o histórico dependem da configuração e disponibilidade do Supabase.
- PDFs sem texto extraível, como documentos digitalizados sem OCR, não fornecem conteúdo textual para busca.
- A geração de SQL e de respostas usa um modelo de linguagem; valide a consulta e a resposta antes de usá-las em decisões importantes.
