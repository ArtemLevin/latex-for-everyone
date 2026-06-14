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
            const error = new Error(message);
            error.status = response.status;
            error.retryAfter = response.headers.get('Retry-After') || '';
            throw error;
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
        pdfPreviewDocument = null;
        pdfPreviewUrl = '';
        const rendered = renderLatex(editor.getValue());
        document.getElementById('previewContent').innerHTML = rendered;
    }

    function showPdfPreview(pdfUrl) {
        ensureAdjacentPreviewVisible();
        activateRenderedPreviewTab();
        setPreviewPdfMode(true);
        const url = resolveApiUrl(pdfUrl);
        pdfPreviewUrl = url;
        pdfPreviewDocument = null;
        pdfPreviewPage = 1;
        pdfPreviewFitMode = 'width';
        pdfPreviewScale = 1;
        document.getElementById('previewContent').innerHTML = buildPdfPreviewShell('Загрузка PDF...');

        loadPdfPreview(url).catch(error => {
            console.error('PDF preview failed', error);
            document.getElementById('previewContent').innerHTML = buildPdfPreviewShell(`Не удалось открыть PDF: ${escapeHtml(error.message || String(error))}`);
        });
    }

    function buildPdfPreviewShell(message = '') {
        return `
            <div class="pdf-preview-shell">
                <div class="pdf-preview-toolbar">
                    <button class="pdf-preview-btn" type="button" onclick="changePdfPreviewPage(-1)" aria-label="Предыдущая страница">‹</button>
                    <span class="pdf-preview-page-info" id="pdfPreviewPageInfo">${message || 'Страница —'}</span>
                    <button class="pdf-preview-btn" type="button" onclick="changePdfPreviewPage(1)" aria-label="Следующая страница">›</button>
                    <span class="pdf-preview-spacer"></span>
                    <button class="pdf-preview-btn" type="button" onclick="setPdfPreviewFit('page')">Вся страница</button>
                    <button class="pdf-preview-btn active" type="button" onclick="setPdfPreviewFit('width')">По ширине</button>
                    <button class="pdf-preview-btn" type="button" onclick="changePdfPreviewZoom(-0.1)">−</button>
                    <span class="pdf-preview-zoom" id="pdfPreviewZoom">100%</span>
                    <button class="pdf-preview-btn" type="button" onclick="changePdfPreviewZoom(0.1)">+</button>
                </div>
                <div class="pdf-preview-stage" id="pdfPreviewStage">
                    <canvas class="pdf-preview-canvas" id="pdfPreviewCanvas"></canvas>
                </div>
            </div>
        `;
    }

    function getPdfJsLib() {
        if (!window.pdfjsLib) {
            throw new Error('PDF.js не загружен');
        }
        return window.pdfjsLib;
    }

    async function loadPdfPreview(url) {
        const pdfjsLib = getPdfJsLib();
        const loadingTask = pdfjsLib.getDocument(url);
        pdfPreviewDocument = await loadingTask.promise;
        await renderPdfPreviewPage();
    }

    async function renderPdfPreviewPage() {
        if (!pdfPreviewDocument) return;
        const page = await pdfPreviewDocument.getPage(pdfPreviewPage);
        const stage = document.getElementById('pdfPreviewStage');
        const canvas = document.getElementById('pdfPreviewCanvas');
        if (!stage || !canvas) return;

        const baseViewport = page.getViewport({ scale: 1 });
        const availableWidth = Math.max(stage.clientWidth - 32, 320);
        const availableHeight = Math.max(stage.clientHeight - 32, 320);
        let scale = pdfPreviewScale;
        if (pdfPreviewFitMode === 'width') {
            scale = availableWidth / baseViewport.width;
        } else if (pdfPreviewFitMode === 'page') {
            scale = Math.min(availableWidth / baseViewport.width, availableHeight / baseViewport.height);
        }
        scale = Math.min(Math.max(scale, 0.25), 4);

        const viewport = page.getViewport({ scale });
        const ratio = window.devicePixelRatio || 1;
        const context = canvas.getContext('2d');
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        if (window.pdfPreviewRenderTask) {
            window.pdfPreviewRenderTask.cancel();
            window.pdfPreviewRenderTask = null;
        }
        const renderTask = page.render({ canvasContext: context, viewport });
        window.pdfPreviewRenderTask = renderTask;
        try {
            await renderTask.promise;
        } catch (error) {
            if (error?.name === 'RenderingCancelledException') return;
            throw error;
        } finally {
            if (window.pdfPreviewRenderTask === renderTask) {
                window.pdfPreviewRenderTask = null;
            }
        }
        updatePdfPreviewControls(scale);
    }

    function updatePdfPreviewControls(scale) {
        const pageInfo = document.getElementById('pdfPreviewPageInfo');
        const zoomInfo = document.getElementById('pdfPreviewZoom');
        if (pageInfo && pdfPreviewDocument) {
            pageInfo.textContent = `Страница ${pdfPreviewPage} из ${pdfPreviewDocument.numPages}`;
        }
        if (zoomInfo) {
            zoomInfo.textContent = `${Math.round(scale * 100)}%`;
        }
        document.querySelectorAll('.pdf-preview-btn').forEach(button => button.classList.remove('active'));
        document.querySelector(`.pdf-preview-btn[onclick="setPdfPreviewFit('${pdfPreviewFitMode}')"]`)?.classList.add('active');
    }

    function changePdfPreviewPage(delta) {
        if (!pdfPreviewDocument) return;
        pdfPreviewPage = Math.min(Math.max(pdfPreviewPage + delta, 1), pdfPreviewDocument.numPages);
        renderPdfPreviewPage();
    }

    function setPdfPreviewFit(mode) {
        pdfPreviewFitMode = mode;
        renderPdfPreviewPage();
    }

    function changePdfPreviewZoom(delta) {
        pdfPreviewFitMode = 'custom';
        pdfPreviewScale = Math.min(Math.max(pdfPreviewScale + delta, 0.25), 4);
        renderPdfPreviewPage();
    }

    window.addEventListener('resize', () => {
        if (!pdfPreviewDocument || !document.getElementById('previewContent')?.classList.contains('pdf-preview-content')) return;
        clearTimeout(pdfPreviewResizeTimer);
        pdfPreviewResizeTimer = setTimeout(renderPdfPreviewPage, 120);
    });

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
        { name: 'Уроки: обновить workflow', shortcut: '', action: () => refreshLessonsWorkflow() },
        { name: 'Экспорт в PDF', shortcut: '', action: () => exportPDF() },
        { name: 'Экспорт в HTML', shortcut: '', action: () => exportHTML() },
        { name: 'Экспорт в .tex', shortcut: '', action: () => exportLatex() },
        { name: 'Настройки', shortcut: 'Ctrl+,', action: () => toggleSettings() },
        { name: 'Переключить тему', shortcut: '', action: () => toggleTheme() },
        { name: 'Полноэкранный режим', shortcut: 'F11', action: () => toggleFullscreen() },
    ];
