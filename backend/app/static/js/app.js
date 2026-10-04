/**
 * Enterprise Data Assistant - Frontend Application Logic
 * Módulo da interface para uploads, streaming SSE e renderização do chat.
 */

document.addEventListener("DOMContentLoaded", () => {
    // Referências aos elementos da página.
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const uploadStatus = document.getElementById("upload-status");
    const fileListContainer = document.getElementById("file-list");
    const fileCountSpan = document.getElementById("file-count");
    const chatForm = document.getElementById("chat-form");
    const queryInput = document.getElementById("query-input");
    const btnSend = document.getElementById("btn-send");
    const chatMessagesContainer = document.getElementById("chat-messages");
    const btnNewSession = document.getElementById("btn-new-session");
    const btnExportChat = document.getElementById("btn-export-chat");

    // Estado da interface.
    let currentSessionId = localStorage.getItem("assistant_session_id") || null;
    let isProcessing = false;

    // Inicializa a sessão e carrega o catálogo de documentos.
    initSession();
    loadDocumentsCatalog();

    // --------------------------------------------------------------------------
    // 1. Gerenciamento da sessão.
    // --------------------------------------------------------------------------
    async function initSession() {
        if (!currentSessionId) {
            try {
                const res = await fetch("/api/v1/chat/session", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ title: "Sessao Inicial" })
                });
                if (res.ok) {
                    const data = await res.json();
                    currentSessionId = data.session_id;
                    localStorage.setItem("assistant_session_id", currentSessionId);
                }
            } catch (err) {
                console.warn("Falha ao inicializar a sessão remota; gerando um identificador local:", err);
                currentSessionId = crypto.randomUUID();
            }
        }
    }

    if (btnNewSession) {
        btnNewSession.addEventListener("click", async () => {
            currentSessionId = crypto.randomUUID();
            localStorage.setItem("assistant_session_id", currentSessionId);
            chatMessagesContainer.innerHTML = `
                <div class="welcome-card max-w-2xl mx-auto my-12 p-6 rounded-xl border border-slate-800 bg-slate-900/40 text-center space-y-4">
                    <div class="inline-flex p-3 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                        </svg>
                    </div>
                    <h2 class="text-lg font-semibold text-white">Nova Sessao de Analise Iniciada</h2>
                    <p class="text-xs text-slate-400 max-w-md mx-auto">
                    Faca novas perguntas sobre seus dados ou realize o upload de novos arquivos.
                    </p>
                </div>
            `;
            initQuickPrompts();
        });
    }

    if (btnExportChat) {
        btnExportChat.addEventListener("click", () => {
            const bubbles = chatMessagesContainer.querySelectorAll(".flex.justify-end, .flex.justify-start.space-x-3");
            if (bubbles.length === 0) {
                alert("Nenhuma mensagem para exportar nesta sessao.");
                return;
            }

            let report = `# Relatorio de Analise de Dados\n`;
            report += `Data de Emissao: ${new Date().toLocaleString("pt-BR")}\n`;
            report += `Identificador da Sessao: ${currentSessionId || "N/A"}\n\n---\n\n`;

            bubbles.forEach((bubble) => {
                const userBox = bubble.querySelector(".bg-blue-600");
                const aiBox = bubble.querySelector(".markdown-body");

                if (userBox) {
                    report += `### Pergunta do Usuario:\n${userBox.innerText.trim()}\n\n`;
                } else if (aiBox) {
                    const sqlTag = bubble.querySelector("details.sql-accordion pre code");
                    if (sqlTag) {
                        report += `**Consulta SQL Executada no DuckDB:**\n\`\`\`sql\n${sqlTag.innerText.trim()}\n\`\`\`\n\n`;
                    }
                    report += `### Resposta do Assistente:\n${aiBox.innerText.trim()}\n\n---\n\n`;
                }
            });

            const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `relatorio_analise_${new Date().toISOString().slice(0, 10)}.md`;
            a.click();
            URL.revokeObjectURL(url);
        });
    }

    // --------------------------------------------------------------------------
    // 2. Envio de arquivos por arraste ou seletor.
    // --------------------------------------------------------------------------
    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("drag-over");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("drag-over");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("drag-over");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            uploadFiles(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            uploadFiles(e.target.files);
        }
    });

    async function uploadFiles(files) {
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append("files", files[i]);
        }

        uploadStatus.classList.remove("hidden");
        uploadStatus.textContent = `Enviando e indexando ${files.length} arquivo(s)...`;

        try {
            const response = await fetch("/api/v1/upload", {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Erro no upload dos arquivos.");
            }

            uploadStatus.textContent = "Upload e indexacao concluidos com sucesso.";
            uploadStatus.classList.replace("text-blue-400", "text-emerald-400");
            uploadStatus.classList.replace("bg-blue-500/10", "bg-emerald-500/10");

            setTimeout(() => {
                uploadStatus.classList.add("hidden");
                uploadStatus.classList.replace("text-emerald-400", "text-blue-400");
                uploadStatus.classList.replace("bg-emerald-500/10", "bg-blue-500/10");
            }, 3000);

            loadDocumentsCatalog();
        } catch (error) {
            uploadStatus.textContent = `Falha: ${error.message}`;
            uploadStatus.classList.replace("text-blue-400", "text-red-400");
            uploadStatus.classList.replace("bg-blue-500/10", "bg-red-500/10");
        } finally {
            fileInput.value = "";
        }
    }

    async function loadDocumentsCatalog() {
        try {
            const response = await fetch("/api/v1/documents");
            if (response.ok) {
                const docs = await response.json();
                renderFileList(docs);
            }
        } catch (err) {
            console.error("Erro ao carregar catalogo de documentos:", err);
        }
    }

    function renderFileList(documents) {
        fileCountSpan.textContent = documents.length;

        if (!documents || documents.length === 0) {
            fileListContainer.innerHTML = `<p class="text-xs text-slate-500 text-center py-6">Nenhum documento carregado nesta sessao.</p>`;
            return;
        }

        fileListContainer.innerHTML = documents.map(doc => {
            const isExcel = doc.file_type === "excel" || doc.file_type === "csv";
            const badgeColor = isExcel ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-rose-500/10 text-rose-400 border-rose-500/20";
            const typeLabel = doc.file_type.toUpperCase();

            let detail = "";
            if (isExcel && doc.metadata && doc.metadata.sheets) {
                const sheets = doc.metadata.sheets;
                const totalRows = sheets.reduce((acc, s) => acc + (s.row_count || 0), 0);
                detail = `${sheets.length} aba(s), ${totalRows} linhas`;
            } else if (doc.file_type === "pdf" && doc.metadata && doc.metadata.total_pages) {
                detail = `${doc.metadata.total_pages} pagina(s)`;
            } else {
                detail = `${(doc.file_size_bytes / 1024).toFixed(1)} KB`;
            }

            return `
                <div class="p-2.5 rounded-lg border border-slate-800 bg-slate-900/60 flex items-start justify-between space-x-2">
                    <div class="flex-1 min-w-0">
                        <p class="text-xs font-medium text-slate-200 truncate" title="${doc.filename}">${doc.filename}</p>
                        <p class="text-[11px] text-slate-500">${detail}</p>
                    </div>
                    <span class="px-2 py-0.5 text-[10px] font-semibold tracking-wider rounded border ${badgeColor}">
                        ${typeLabel}
                    </span>
                </div>
            `;
        }).join("");
    }

    // --------------------------------------------------------------------------
    // 3. Conversa e transmissão em tempo real (SSE).
    // --------------------------------------------------------------------------
    function initQuickPrompts() {
        document.querySelectorAll(".quick-prompt").forEach(btn => {
            btn.addEventListener("click", () => {
                queryInput.value = btn.textContent.trim();
                triggerSubmit();
            });
        });
    }
    initQuickPrompts();

    queryInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            triggerSubmit();
        }
    });

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        triggerSubmit();
    });

    function triggerSubmit() {
        const query = queryInput.value.trim();
        if (!query || isProcessing) return;

        // Remove o cartão de boas-vindas, se estiver visível.
        const welcomeCard = document.querySelector(".welcome-card");
        if (welcomeCard) welcomeCard.remove();

        // Exibe a pergunta do usuário.
        appendUserMessage(query);
        queryInput.value = "";
        adjustTextareaHeight();

        // Inicia a requisição de streaming.
        executeStreamingQuery(query);
    }

    function adjustTextareaHeight() {
        queryInput.style.height = "auto";
        queryInput.style.height = Math.min(queryInput.scrollHeight, 128) + "px";
    }
    queryInput.addEventListener("input", adjustTextareaHeight);

    function appendUserMessage(text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = "flex justify-end";
        msgDiv.innerHTML = `
            <div class="max-w-xl rounded-2xl rounded-tr-none px-4 py-3 bg-blue-600 text-white text-sm shadow-md">
                ${escapeHtml(text)}
            </div>
        `;
        chatMessagesContainer.appendChild(msgDiv);
        scrollToBottom();
    }

    async function executeStreamingQuery(query) {
        isProcessing = true;
        btnSend.disabled = true;

        // Cria o contêiner da resposta do assistente.
        const assistantBubble = document.createElement("div");
        assistantBubble.className = "flex justify-start space-x-3";
        assistantBubble.innerHTML = `
            <div class="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-semibold text-blue-400 flex-shrink-0">
                AI
            </div>
            <div class="flex-1 max-w-3xl space-y-2">
                <!-- Indicador de estado do processamento. -->
                <div class="status-indicator inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">
                    <span class="w-1.5 h-1.5 rounded-full bg-blue-400 mr-2 animate-pulse"></span>
                    <span class="status-text">Processando pergunta...</span>
                </div>
                <!-- Consulta SQL, quando aplicável. -->
                <div class="sql-container hidden"></div>
                <!-- Resposta em Markdown e indicador de transmissão. -->
                <div class="markdown-body streaming-cursor text-slate-200"></div>
            </div>
        `;
        chatMessagesContainer.appendChild(assistantBubble);
        scrollToBottom();

        const statusIndicator = assistantBubble.querySelector(".status-indicator");
        const statusText = assistantBubble.querySelector(".status-text");
        const sqlContainer = assistantBubble.querySelector(".sql-container");
        const markdownBody = assistantBubble.querySelector(".markdown-body");

        let accumulatedText = "";

        try {
            const response = await fetch("/api/v1/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: query,
                    session_id: currentSessionId,
                }),
            });

            if (!response.ok) {
                throw new Error(`Falha no servidor (${response.status})`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop(); // Mantém no buffer o último evento incompleto.

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const event = JSON.parse(line.substring(6));

                            if (event.type === "status") {
                                statusText.textContent = event.message;
                            } else if (event.type === "sql") {
                                sqlContainer.classList.remove("hidden");
                                sqlContainer.innerHTML = `
                                    <details class="sql-accordion">
                                        <summary>
                                            <span>Consulta SQL Executada no DuckDB</span>
                                            <span class="text-[10px] text-slate-500 font-mono">Clique para expandir</span>
                                        </summary>
                                        <pre><code>${escapeHtml(event.query)}</code></pre>
                                    </details>
                                `;
                            } else if (event.type === "token") {
                                accumulatedText += event.content;
                                markdownBody.innerHTML = marked.parse(accumulatedText);
                                scrollToBottom();
                            } else if (event.type === "done") {
                                statusIndicator.remove();
                                markdownBody.classList.remove("streaming-cursor");
                            }
                        } catch (parseErr) {
                            console.warn("Erro ao decodificar frame SSE:", parseErr, line);
                        }
                    }
                }
            }

        } catch (error) {
            statusIndicator.remove();
            markdownBody.classList.remove("streaming-cursor");
            markdownBody.innerHTML += `<p class="text-rose-400 text-xs mt-2">[Erro]: ${escapeHtml(error.message)}</p>`;
        } finally {
            markdownBody.classList.remove("streaming-cursor");
            isProcessing = false;
            btnSend.disabled = false;
            queryInput.focus();
            scrollToBottom();
        }
    }

    function scrollToBottom() {
        chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
    }

    function escapeHtml(string) {
        const div = document.createElement("div");
        div.innerText = string;
        return div.innerHTML;
    }
});
