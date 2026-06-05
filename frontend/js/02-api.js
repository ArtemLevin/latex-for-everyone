    // ==================== BACKEND API ====================
    async function apiRequest(path, options = {}) {
        const response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            }
        });

        if (!response.ok) {
            let message = `HTTP ${response.status}`;
            try {
                const data = await response.json();
                message = data.detail || message;
            } catch (e) {
                message = response.statusText || message;
            }
            throw new Error(message);
        }

        if (response.status === 204) return null;
        return response.json();
    }

    function resolveApiUrl(url) {
        return new URL(url, API_ORIGIN).toString();
    }

    function setBackendAvailability(isAvailable) {
        backendAvailable = isAvailable;
        document.body.dataset.backend = isAvailable ? 'online' : 'offline';
        const lastCompiled = document.getElementById('lastCompiled');
        if (lastCompiled) {
            lastCompiled.textContent = isAvailable
                ? `Backend: подключён (${API_BASE_URL})`
                : `Backend: недоступен (${API_BASE_URL})`;
        }
    }

    function setEditorContent(content) {
        suppressEditorChange = true;
        try {
            editor.setValue(content || '');
        } finally {
            suppressEditorChange = false;
        }
    }

    async function bootstrapBackend() {
        try {
            await apiRequest('/health');
            setBackendAvailability(true);
            await loadOrCreateProject();
            await loadProjectFiles();
            await loadTemplates();
            openInitialFile();
            renderFileTree();
            showToast('Соединение с backend установлено. Нажмите «Компиляция», чтобы собрать PDF.', 'success');
        } catch (error) {
            setBackendAvailability(false);
            renderFileTree();
            showToast(`Backend недоступен: ${error.message}. Документ открыт без автокомпиляции.`, 'error');
        }
    }

    async function loadOrCreateProject() {
        const savedProjectId = localStorage.getItem(LOCAL_PROJECT_KEY);
        if (savedProjectId) {
            try {
                currentProject = await apiRequest(`/projects/${savedProjectId}`);
                document.getElementById('projectNameInput').value = currentProject.name;
                return;
            } catch (error) {
                localStorage.removeItem(LOCAL_PROJECT_KEY);
            }
        }

        currentProject = await apiRequest('/projects/', {
            method: 'POST',
            body: JSON.stringify({
                name: document.getElementById('projectNameInput').value || 'Мой документ',
                is_public: false,
                template: 'article'
            })
        });
        localStorage.setItem(LOCAL_PROJECT_KEY, currentProject.id);
        document.getElementById('projectNameInput').value = currentProject.name;
    }

    async function loadProjectFiles() {
        const backendFiles = await apiRequest(`/files/project/${currentProject.id}`);
        files = {};
        backendFiles.forEach(file => {
            files[file.id] = file;
        });
    }

    async function loadTemplates() {
        templates = await apiRequest('/templates/');
    }

    function openInitialFile() {
        const mainFile = Object.values(files).find(file => file.is_main) || Object.values(files)[0];
        if (!mainFile) return;
        currentFileId = mainFile.id;
        setEditorContent(mainFile.content);
        document.getElementById('currentFileName').textContent = mainFile.name;
    }

    function collectFilesByName() {
        if (currentFileId && files[currentFileId]) {
            files[currentFileId].content = editor.getValue();
        }
        const byName = {};
        Object.values(files).forEach(file => {
            byName[file.name] = file.content || '';
        });
        return byName;
    }

    function showCompileError(message) {
        document.getElementById('errorPanel').classList.add('active');
        document.getElementById('errorText').textContent = message;
        document.getElementById('statusDot').className = 'status-dot error';
        document.getElementById('statusText').textContent = 'Ошибка';
    }

    function setPreviewPdfMode(isPdf) {
        const previewContainer = document.getElementById('previewContainer');
        const previewContent = document.getElementById('previewContent');
        previewContainer?.classList.toggle('pdf-preview-container', isPdf);
        previewContent?.classList.toggle('pdf-preview-content', isPdf);
    }

    function activateRenderedPreviewTab() {
        const previewPane = document.getElementById('previewPane');
        if (!previewPane) return;
        const tabs = previewPane.querySelectorAll('.pane-tab');
        tabs.forEach(tab => tab.classList.remove('active'));
        tabs[0]?.classList.add('active');
    }

    function ensureAdjacentPreviewVisible() {
        const previewPane = document.getElementById('previewPane');
        if (!previewPane) return;
        if (getComputedStyle(previewPane).display === 'none' && typeof setViewMode === 'function') {
            setViewMode('split');
        }
    }

    function showHtmlPreviewFallback() {
        setPreviewPdfMode(false);
        activateRenderedPreviewTab();
        const rendered = renderLatex(editor.getValue());
        document.getElementById('previewContent').innerHTML = rendered;
    }

    function showPdfPreview(pdfUrl) {
        ensureAdjacentPreviewVisible();
        activateRenderedPreviewTab();
        setPreviewPdfMode(true);
        const url = resolveApiUrl(pdfUrl);
        document.getElementById('previewContent').innerHTML = `
            <iframe class="pdf-preview-frame" src="${url}#toolbar=0&navpanes=0" title="PDF preview"></iframe>
        `;
    }

    async function saveCurrentFile() {
        clearTimeout(saveTimeout);
        if (!currentFileId || !files[currentFileId]) return null;
        const file = files[currentFileId];
        file.content = editor.getValue();

        if (!backendAvailable) return file;

        const updated = await apiRequest(`/files/${file.id}`, {
            method: 'PUT',
            body: JSON.stringify({ content: file.content })
        });
        files[updated.id] = updated;
        return updated;
    }

    function scheduleSaveCurrentFile() {
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
            try {
                await saveCurrentFile();
                document.getElementById('statusText').textContent = 'Сохранено';
            } catch (error) {
                showToast(`Ошибка сохранения: ${error.message}`, 'error');
            }
        }, 800);
    }

    const commands = [
        { name: 'Скомпилировать', shortcut: 'Ctrl+Enter', action: () => compileLatex() },
        { name: 'Создать новый файл', shortcut: 'Ctrl+N', action: () => createNewFile() },
        { name: 'Найти и заменить', shortcut: 'Ctrl+H', action: () => toggleFindReplace() },
        { name: 'Показать шаблоны', shortcut: '', action: () => showTemplates() },
        { name: 'AI-генерация LaTeX', shortcut: '', action: () => showGenerationModal() },
        { name: 'Экспорт в PDF', shortcut: '', action: () => exportPDF() },
        { name: 'Экспорт в HTML', shortcut: '', action: () => exportHTML() },
        { name: 'Экспорт в .tex', shortcut: '', action: () => exportLatex() },
        { name: 'Настройки', shortcut: 'Ctrl+,', action: () => toggleSettings() },
        { name: 'Переключить тему', shortcut: '', action: () => toggleTheme() },
        { name: 'Полноэкранный режим', shortcut: 'F11', action: () => toggleFullscreen() },
    ];
