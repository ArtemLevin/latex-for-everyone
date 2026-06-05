    // ==================== STATE ====================
    let editor = null;
    let currentProject = null;
    let currentFileId = 'main';
    let autoCompile = false;
    let backendAvailable = false;
    let compileTimeout = null;
    let saveTimeout = null;
    let generationPresets = [];
    let lastGenerationPrompt = '';
    let lastGenerationRawOutput = '';
    let suppressEditorChange = false;
    let contextMenuFileId = null;
    let selectedCommandIndex = 0;

    const LOCAL_PROJECT_KEY = 'latexed_project_id';
    const API_BASE_URL = getApiBaseUrl();
    const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, '');

    function getApiBaseUrl() {
        const configured = window.LATEXED_API_BASE_URL
            || document.querySelector('meta[name="latexed-api-base-url"]')?.content;
        if (configured) return configured.replace(/\/$/, '');

        const isHttp = window.location.protocol === 'http:' || window.location.protocol === 'https:';
        const isLocalFrontend = ['localhost', '127.0.0.1'].includes(window.location.hostname)
            && window.location.port
            && window.location.port !== '8000';
        const origin = isHttp && !isLocalFrontend ? window.location.origin : 'http://localhost:8000';
        return `${origin}/api`;
    }

    let files = {
        main: {
            name: 'main.tex',
            content: `\\documentclass[12pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}
\\usepackage{graphicx}
\\usepackage{hyperref}
\\usepackage{geometry}
\\geometry{margin=1in}

\\title{Введение в линейную алгебру}
\\author{Иванов И.И.}
\\date{\\today}

\\begin{document}

\\maketitle

\\begin{abstract}
В данной работе рассматриваются основные понятия линейной алгебры,
включая векторные пространства, линейные преобразования и собственные значения.
Представлены теоретические основы и практические примеры.
\\end{abstract}

\\section{Введение}

Линейная алгебра является одним из фундаментальных разделов математики.
Она изучает векторные пространства и линейные отображения между ними.

\\subsection{Определения}

\\textbf{Векторное пространство} --- это множество $V$, элементы которого
называются \\textit{векторами}, на котором определены две операции:

\\begin{enumerate}
\\item Сложение векторов: $\\vec{a} + \\vec{b} \\in V$
\\item Умножение на скаляр: $\\alpha \\cdot \\vec{a} \\in V$, где $\\alpha \\in \\mathbb{R}$
\\end{enumerate}

\\section{Матрицы и определители}

\\subsection{Операции с матрицами}

Рассмотрим матрицу $A$ размера $n \\times m$:

$$A = \\begin{pmatrix} a_{11} & a_{12} & \\cdots & a_{1m} \\\\ a_{21} & a_{22} & \\cdots & a_{2m} \\\\ \\vdots & \\vdots & \\ddots & \\vdots \\\\ a_{n1} & a_{n2} & \\cdots & a_{nm} \\end{pmatrix}$$

\\subsection{Определитель}

Определитель матрицы $2 \\times 2$ вычисляется по формуле:

$$\\det(A) = \\begin{vmatrix} a & b \\\\ c & d \\end{vmatrix} = ad - bc$$

Для матрицы $3 \\times 3$ используется правило Саррюса:

$$\\det(A) = a_{11}a_{22}a_{33} + a_{12}a_{23}a_{31} + a_{13}a_{21}a_{32} - a_{13}a_{22}a_{31} - a_{11}a_{23}a_{32} - a_{12}a_{21}a_{33}$$

\\section{Системы линейных уравнений}

Система $n$ линейных уравнений с $m$ неизвестными записывается в виде:

$$\\begin{cases} a_{11}x_1 + a_{12}x_2 + \\cdots + a_{1m}x_m = b_1 \\\\ a_{21}x_1 + a_{22}x_2 + \\cdots + a_{2m}x_m = b_2 \\\\ \\vdots \\\\ a_{n1}x_1 + a_{n2}x_2 + \\cdots + a_{nm}x_m = b_n \\end{cases}$$

В матричной форме: $A\\vec{x} = \\vec{b}$

\\section{Собственные значения и векторы}

\\textbf{Собственное значение} $\\lambda$ и \\textbf{собственный вектор} $\\vec{v}$
матрицы $A$ удовлетворяют уравнению:

$$A\\vec{v} = \\lambda\\vec{v}$$

Характеристическое уравнение:

$$\\det(A - \\lambda I) = 0$$

\\subsection{Пример}

Для матрицы $A = \\begin{pmatrix} 4 & 1 \\\\ 2 & 3 \\end{pmatrix}$:

$$\\det(A - \\lambda I) = \\begin{vmatrix} 4-\\lambda & 1 \\\\ 2 & 3-\\lambda \\end{vmatrix} = (4-\\lambda)(3-\\lambda) - 2 = \\lambda^2 - 7\\lambda + 10$$

Корни: $\\lambda_1 = 5$, $\\lambda_2 = 2$

\\section{Заключение}

Линейная алгебра находит широкое применение в различных областях:

\\begin{itemize}
\\item Физика --- квантовая механика, теория относительности
\\item Информатика --- машинное обучение, компьютерная графика
\\item Экономика --- моделирование, оптимизация
\\item Инженерия --- анализ цепей, теория управления
\\end{itemize}

\\section*{Формулы}

Некоторые важные формулы линейной алгебры:

$$e^{i\\pi} + 1 = 0$$

$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$

$$\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}$$

\\end{document}`
        },
        preamble: {
            name: 'preamble.tex',
            content: `%% Преамбула документа
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath, amssymb, amsthm}
\\usepackage{graphicx}
\\usepackage{hyperref}
\\usepackage{geometry}
\\geometry{margin=1in}

%% Теоремы
\\newtheorem{theorem}{Теорема}
\\newtheorem{lemma}{Лемма}
\\newtheorem{definition}{Определение}
\\newtheorem{example}{Пример}`
        },
        bibliography: {
            name: 'bibliography.bib',
            content: `@book{knuth1997,
author = {Knuth, Donald E.},
title = {The Art of Computer Programming},
year = {1997},
publisher = {Addison-Wesley},
volume = {1}
}

@article{einstein1905,
author = {Einstein, Albert},
title = {Zur Elektrodynamik bewegter Körper},
journal = {Annalen der Physik},
year = {1905},
volume = {322},
pages = {891--921}
}

@book{gilbert_strang,
author = {Strang, Gilbert},
title = {Introduction to Linear Algebra},
year = {2016},
publisher = {Wellesley-Cambridge Press},
edition = {5}
}`
        }
    };

    let templates = [
        {
            name: 'Статья (article)',
            desc: 'Стандартная научная статья с заголовком, аннотацией и секциями',
            content: `\\documentclass[12pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\title{Заголовок статьи}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\maketitle

\\begin{abstract}
Аннотация статьи.
\\end{abstract}

\\section{Введение}
Текст введения.

\\section{Основная часть}
Основной текст.

\\section{Заключение}
Заключение.

\\end{document}`
        },
        {
            name: 'Отчёт (report)',
            desc: 'Отчёт с главами и разделами',
            content: `\\documentclass[12pt,a4paper]{report}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\title{Название отчёта}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\maketitle
\\tableofcontents
\\newpage

\\chapter{Введение}
Текст введения.

\\chapter{Основная часть}
Основной текст.

\\chapter{Заключение}
Заключение.

\\end{document}`
        },
        {
            name: 'Презентация (beamer)',
            desc: 'Презентация для выступления',
            content: `\\documentclass{beamer}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usetheme{Madrid}

\\title{Название презентации}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\frame{\\titlepage}

\\begin{frame}{Введение}
\\begin{itemize}
    \\item Первый пункт
    \\item Второй пункт
    \\item Третий пункт
\\end{itemize}
\\end{frame}

\\begin{frame}{Формулы}
$$E = mc^2$$
\\end{frame}

\\end{document}`
        },
        {
            name: 'Книга (book)',
            desc: 'Книга с главами, частями и оглавлением',
            content: `\\documentclass[12pt,a4paper]{book}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\title{Название книги}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\frontmatter
\\maketitle
\\tableofcontents

\\mainmatter

\\part{Часть первая}

\\chapter{Введение}
Текст главы.

\\chapter{Основы}
Текст главы.

\\part{Часть вторая}

\\chapter{Продвинутые темы}
Текст главы.

\\backmatter

\\end{document}`
        },
        {
            name: 'Письмо (letter)',
            desc: 'Официальное письмо',
            content: `\\documentclass[a4paper]{letter}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}

\\address{Ваш адрес\\\\Город, Индекс}
\\signature{Ваше Имя}

\\begin{document}

\\begin{letter}{Адресат\\\\Организация\\\\Город}

\\opening{Уважаемый(ая),}

Текст письма.

\\closing{С уважением,}

\\end{letter}

\\end{document}`
        },
        {
            name: 'Пустой документ',
            desc: 'Минимальный пустой LaTeX документ',
            content: `\\documentclass[12pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\begin{document}


\\end{document}`
        }
    ];

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
            showToast('Соединение с backend установлено', 'success');
            try {
                await compileLatex();
            } catch (compileError) {
                showCompileError(compileError.message);
            }
        } catch (error) {
            setBackendAvailability(false);
            renderFileTree();
            compileLatexLocal();
            showToast(`Backend недоступен: ${error.message}. Работаем локально.`, 'error');
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

    function showHtmlPreviewFallback() {
        const rendered = renderLatex(editor.getValue());
        document.getElementById('previewContent').innerHTML = rendered;
    }

    function showPdfPreview(pdfUrl) {
        const url = resolveApiUrl(pdfUrl);
        document.getElementById('previewContent').innerHTML = `
            <iframe src="${url}" title="PDF preview" style="width:100%;height:100%;min-height:70vh;border:0;background:white;border-radius:8px;"></iframe>
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
        { name: 'Скомпилировать', shortcut: 'Ctrl+Enter', action: compileLatex },
        { name: 'Создать новый файл', shortcut: 'Ctrl+N', action: createNewFile },
        { name: 'Найти и заменить', shortcut: 'Ctrl+H', action: toggleFindReplace },
        { name: 'Показать шаблоны', shortcut: '', action: showTemplates },
        { name: 'AI-генерация LaTeX', shortcut: '', action: showGenerationModal },
        { name: 'Экспорт в PDF', shortcut: '', action: exportPDF },
        { name: 'Экспорт в HTML', shortcut: '', action: exportHTML },
        { name: 'Экспорт в .tex', shortcut: '', action: exportLatex },
        { name: 'Настройки', shortcut: 'Ctrl+,', action: toggleSettings },
        { name: 'Переключить тему', shortcut: '', action: toggleTheme },
        { name: 'Полноэкранный режим', shortcut: 'F11', action: toggleFullscreen },
    ];

    // ==================== INIT ====================
    function init() {
        editor = CodeMirror(document.getElementById('codeEditor'), {
            value: files.main.content,
            mode: 'stex',
            theme: 'monokai',
            lineNumbers: true,
            lineWrapping: true,
            autoCloseBrackets: true,
            matchBrackets: true,
            styleActiveLine: true,
            foldGutter: true,
            gutters: ['CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            keyMap: 'sublime',
            extraKeys: {
                'Ctrl-Enter': compileLatex,
                'Ctrl-S': function(cm) { saveFile(); },
                'Ctrl-H': function(cm) { toggleFindReplace(); },
                'Ctrl-Shift-P': function(cm) { toggleCommandPalette(); },
                'Ctrl-/': function(cm) { toggleComment(); },
                'Ctrl-Space': function(cm) { cm.showHint({ hint: CodeMirror.hint.anyword }); }
            }
        });

        editor.on('change', function() {
            if (!currentFileId || !files[currentFileId]) return;
            files[currentFileId].content = editor.getValue();
            updateWordCount();
            if (!suppressEditorChange) {
                scheduleSaveCurrentFile();
            }
            if (!suppressEditorChange && autoCompile) {
                clearTimeout(compileTimeout);
                const delay = parseInt(document.getElementById('compileDelay').value);
                compileTimeout = setTimeout(compileLatex, delay);
            }
        });

        editor.on('cursorActivity', function() {
            const cursor = editor.getCursor();
            document.getElementById('cursorPosition').textContent =
                `Строка ${cursor.line + 1}, Столбец ${cursor.ch + 1}`;
        });

        renderFileTree();
        updateWordCount();
        document.getElementById('projectNameInput').addEventListener('blur', saveProjectName);
        document.getElementById('projectNameInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                e.target.blur();
            }
        });
        bootstrapBackend();

        // Resizer
        initResizer();

        // Close menus on click outside
        document.addEventListener('click', function(e) {
            const contextMenu = document.getElementById('contextMenu');
            if (!contextMenu.contains(e.target)) {
                contextMenu.classList.remove('active');
            }
            const exportMenu = document.getElementById('exportMenu');
            if (!exportMenu.contains(e.target) && !e.target.closest('.dropdown')) {
                exportMenu.classList.remove('active');
            }
            const commandPalette = document.getElementById('commandPalette');
            if (!commandPalette.contains(e.target) && !e.target.closest('[onclick*="commandPalette"]')) {
                // keep open
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                compileLatex();
            }
            if (e.ctrlKey && e.shiftKey && e.key === 'P') {
                e.preventDefault();
                toggleCommandPalette();
            }
            if (e.ctrlKey && e.key === 'h' && !e.shiftKey) {
                // Don't prevent - let CodeMirror handle it
            }
            if (e.key === 'Escape') {
                closeModal('templateModal');
                closeModal('generationModal');
                closeModal('settingsModal');
                document.getElementById('commandPalette').classList.remove('active');
                document.getElementById('contextMenu').classList.remove('active');
            }
            if (e.key === 'F11') {
                e.preventDefault();
                toggleFullscreen();
            }
        });
    }

    // ==================== FILE MANAGEMENT ====================
    function renderFileTree() {
        const tree = document.getElementById('fileTree');
        tree.innerHTML = '';
        Object.keys(files).forEach(id => {
            const file = files[id];
            const item = document.createElement('div');
            item.className = `file-item ${id === currentFileId ? 'active' : ''}`;
            item.dataset.id = id;
            item.onclick = function() { switchFile(id); };
            item.oncontextmenu = function(e) { showContextMenu(e, id); };

            const icon = file.name.endsWith('.tex')
                ? '<svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>'
                : '<svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';

            item.innerHTML = `
                ${icon}
                <span class="file-name">${file.name}</span>
                <div class="file-actions">
                    <button class="file-action-btn" onclick="event.stopPropagation(); renameFile('${id}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                        </svg>
                    </button>
                    <button class="file-action-btn delete" onclick="event.stopPropagation(); deleteFile('${id}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>
            `;
            tree.appendChild(item);
        });
    }

    async function switchFile(id) {
        if (!files[id]) return;
        try {
            await saveCurrentFile();
        } catch (error) {
            showToast(`Ошибка сохранения текущего файла: ${error.message}`, 'error');
        }
        currentFileId = id;
        setEditorContent(files[id].content);
        editor.refresh();
        editor.focus();
        document.getElementById('currentFileName').textContent = files[id].name;
        renderFileTree();
        if (autoCompile) {
            compileLatex();
        } else {
            compileLatexLocal();
        }
    }

    async function createNewFile() {
        const name = prompt('Имя файла:', 'new_document.tex');
        if (!name) return;

        try {
            if (backendAvailable && currentProject) {
                const file = await apiRequest(`/files/project/${currentProject.id}`, {
                    method: 'POST',
                    body: JSON.stringify({ name, content: '', is_main: false })
                });
                files[file.id] = file;
                await switchFile(file.id);
            } else {
                const id = 'file_' + Date.now();
                files[id] = { id, name: name, content: '', is_main: false };
                await switchFile(id);
            }
            showToast('Файл создан', 'success');
        } catch (error) {
            showToast(`Ошибка создания файла: ${error.message}`, 'error');
        }
    }

    async function deleteFile(id) {
        if (Object.keys(files).length <= 1) {
            showToast('Нельзя удалить последний файл', 'error');
            return;
        }
        if (!confirm(`Удалить файл "${files[id].name}"?`)) return;

        try {
            if (backendAvailable) {
                await apiRequest(`/files/${id}`, { method: 'DELETE' });
            }
            delete files[id];
            if (currentFileId === id) {
                await switchFile(Object.keys(files)[0]);
            } else {
                renderFileTree();
            }
            showToast('Файл удалён', 'info');
        } catch (error) {
            showToast(`Ошибка удаления файла: ${error.message}`, 'error');
        }
    }

    async function renameFile(id) {
        const newName = prompt('Новое имя:', files[id].name);
        if (!newName || !newName.trim()) return;

        try {
            if (backendAvailable) {
                const updated = await apiRequest(`/files/${id}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name: newName.trim() })
                });
                delete files[id];
                files[updated.id] = updated;
                if (currentFileId === id) currentFileId = updated.id;
            } else {
                files[id].name = newName.trim();
            }
            renderFileTree();
            if (id === currentFileId || files[currentFileId]?.name === newName.trim()) {
                document.getElementById('currentFileName').textContent = newName.trim();
            }
            showToast('Файл переименован', 'success');
        } catch (error) {
            showToast(`Ошибка переименования файла: ${error.message}`, 'error');
        }
    }

    // ==================== CONTEXT MENU ====================
    function showContextMenu(e, id) {
        e.preventDefault();
        contextMenuFileId = id;
        const menu = document.getElementById('contextMenu');
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
        menu.classList.add('active');
    }

    async function contextAction(action) {
        document.getElementById('contextMenu').classList.remove('active');
        if (!contextMenuFileId) return;
        switch (action) {
            case 'rename':
                renameFile(contextMenuFileId);
                break;
            case 'duplicate':
                try {
                    const source = files[contextMenuFileId];
                    const copyName = 'copy_' + source.name;
                    if (backendAvailable && currentProject) {
                        const file = await apiRequest(`/files/project/${currentProject.id}`, {
                            method: 'POST',
                            body: JSON.stringify({ name: copyName, content: source.content || '', is_main: false })
                        });
                        files[file.id] = file;
                        await switchFile(file.id);
                    } else {
                        const id = 'file_' + Date.now();
                        files[id] = { id, name: copyName, content: source.content || '', is_main: false };
                        await switchFile(id);
                    }
                    showToast('Файл дублирован', 'success');
                } catch (error) {
                    showToast(`Ошибка дублирования файла: ${error.message}`, 'error');
                }
                break;
            case 'delete':
                deleteFile(contextMenuFileId);
                break;
        }
    }

    // ==================== COMPILATION ====================
    async function compileLatex() {
        const btn = document.getElementById('compileBtn');
        btn.classList.add('compiling');
        btn.innerHTML = '<div class="spinner"></div><span>Компиляция...</span>';

        try {
            if (backendAvailable && currentProject) {
                await saveCurrentFile();
                const allFiles = collectFilesByName();
                const mainFile = Object.values(files).find(file => file.is_main) || files[currentFileId];
                const result = await apiRequest('/compile/', {
                    method: 'POST',
                    body: JSON.stringify({
                        project_id: currentProject.id,
                        main_file_content: mainFile?.content || editor.getValue(),
                        all_files: allFiles
                    })
                });

                if (result.status === 'success') {
                    document.getElementById('errorPanel').classList.remove('active');
                    document.getElementById('statusDot').className = 'status-dot';
                    document.getElementById('statusText').textContent = result.compile_time
                        ? `Скомпилировано за ${result.compile_time}`
                        : 'Скомпилировано';
                    if (result.pdf_url) {
                        showPdfPreview(result.pdf_url);
                    } else {
                        showHtmlPreviewFallback();
                    }
                } else {
                    showCompileError(result.error || 'Ошибка компиляции');
                }
            } else {
                compileLatexLocal();
            }
            document.getElementById('lastCompiled').textContent = 'Последняя компиляция: ' + new Date().toLocaleTimeString('ru');
        } catch (e) {
            showCompileError(e.message);
            if (!backendAvailable) {
                compileLatexLocal();
            }
        } finally {
            btn.classList.remove('compiling');
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>Компиляция</span>';
        }
    }

    function compileLatexLocal() {
        try {
            const content = editor.getValue();
            const rendered = renderLatex(content);
            document.getElementById('previewContent').innerHTML = rendered;
            document.getElementById('errorPanel').classList.remove('active');
            document.getElementById('statusDot').className = 'status-dot';
            document.getElementById('statusText').textContent = 'Локальный preview';
        } catch (e) {
            showCompileError(e.message);
        }
    }

    function renderLatex(content) {
        let html = content;

        // Remove comments
        html = html.replace(/%[^\n]*/g, '');

        // Extract preamble
        const preambleMatch = html.match(/\\documentclass\{[^}]+\}([\s\S]*?)\\begin\{document\}/);
        const preamble = preambleMatch ? preambleMatch[1] : '';

        // Extract title, author, date
        const titleMatch = html.match(/\\title\{([^}]*)\}/);
        const authorMatch = html.match(/\\author\{([^}]*)\}/);
        const dateMatch = html.match(/\\date\{([^}]*)\}/);

        // Process document body
        let body = html.replace(/\\documentclass\{[^}]+\}[\s\S]*?\\begin\{document\}/, '');
        body = body.replace(/\\end\{document\}[\s\S]*$/, '');

        let result = '';

        // Title/Author/Date
        if (titleMatch) {
            const title = processInlineLatex(titleMatch[1]);
            result += `<h1>${title}</h1>`;
            if (authorMatch) {
                result += `<p class="author">${processInlineLatex(authorMatch[1])}</p>`;
            }
            if (dateMatch) {
                const dateVal = dateMatch[1];
                result += `<p class="date">${dateVal === '\\today' ? new Date().toLocaleDateString('ru') : processInlineLatex(dateVal)}</p>`;
            }
            result += '<hr style="border: none; border-top: 1px solid #ccc; margin: 1.5em 0;">';
        }

        // Abstract
        body = body.replace(/\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/g, function(m, c) {
            return `<div class="abstract">${processInlineLatex(c.trim())}</div>`;
        });

        // Sections
        body = body.replace(/\\section\*?\{([^}]*)\}/g, '<h2>$1</h2>');
        body = body.replace(/\\subsection\*?\{([^}]*)\}/g, '<h3>$1</h3>');
        body = body.replace(/\\subsubsection\*?\{([^}]*)\}/g, '<h4>$1</h4>');

        // Bold, Italic, Underline
        body = body.replace(/\\textbf\{([^}]*)\}/g, '<strong>$1</strong>');
        body = body.replace(/\\textit\{([^}]*)\}/g, '<em>$1</em>');
        body = body.replace(/\\underline\{([^}]*)\}/g, '<u>$1</u>');
        body = body.replace(/\\texttt\{([^}]*)\}/g, '<code style="background:#f5f5f5;padding:2px 4px;border-radius:3px;font-family:monospace">$1</code>');
        body = body.replace(/\\emph\{([^}]*)\}/g, '<em>$1</em>');
        body = body.replace(/\\textsc\{([^}]*)\}/g, '<span style="font-variant:small-caps">$1</span>');

        // Footnote
        body = body.replace(/\\footnote\{([^}]*)\}/g, '<sup style="color:#6366f1;cursor:pointer" title="$1">†</sup>');

        // New paragraph
        body = body.replace(/\n\n/g, '</p><p>');
        body = body.replace(/\\\\/g, '<br>');

        // Line breaks within paragraphs
        body = body.replace(/\n/g, ' ');

        // Display equations $$...$$
        body = body.replace(/\$\$([\s\S]*?)\$\$/g, function(m, eq) {
            try {
                const rendered = katex.renderToString(eq.trim(), { displayMode: true, throwOnError: false });
                return `<div class="equation-block">${rendered}</div>`;
            } catch (e) {
                return `<div class="equation-block" style="color:red;font-family:monospace">${eq}</div>`;
            }
        });

        // Inline equations $...$
        body = body.replace(/\$([^$]+?)\$/g, function(m, eq) {
            try {
                return katex.renderToString(eq.trim(), { displayMode: false, throwOnError: false });
            } catch (e) {
                return `<span style="color:red;font-family:monospace">${eq}</span>`;
            }
        });

        // Itemize
        body = body.replace(/\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}/g, function(m, c) {
            const items = c.replace(/\\item\s*/g, '<li>').replace(/<\/li>/g, '</li>');
            return `<ul>${items}</ul>`;
        });

        // Enumerate
        body = body.replace(/\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}/g, function(m, c) {
            const items = c.replace(/\\item\s*/g, '<li>').replace(/<\/li>/g, '</li>');
            return `<ol>${items}</ol>`;
        });

        // Table
        body = body.replace(/\\begin\{table\}[\s\S]*?\\begin\{tabular\}\{[^}]*\}([\s\S]*?)\\end\{tabular\}[\s\S]*?\\end\{table\}/g, function(m, c) {
            let tableHtml = '<table>';
            const rows = c.trim().split('\\\\').map(r => r.trim()).filter(r => r);
            rows.forEach((row, i) => {
                const tag = i === 0 ? 'th' : 'td';
                const cells = row.replace(/\\hline/g, '').split('&').map(c => c.trim());
                tableHtml += '<tr>' + cells.map(c => `<${tag}>${processInlineLatex(c)}</${tag}>`).join('') + '</tr>';
            });
            tableHtml += '</table>';
            return tableHtml;
        });

        // Figure
        body = body.replace(/\\begin\{figure\}[\s\S]*?\\end\{figure\}/g, function(m) {
            const caption = m.match(/\\caption\{([^}]*)\}/);
            return `<figure style="text-align:center;margin:1.5em 0">
                <div style="background:#f0f0f0;padding:40px;border-radius:8px;color:#999">[Изображение]</div>
                ${caption ? `<figcaption style="margin-top:8px;font-size:0.9em;color:#666">${caption[1]}</figcaption>` : ''}
            </figure>`;
        });

        // Centering
        body = body.replace(/\\centering/g, '');

        // Clear page
        body = body.replace(/\\clearpage/g, '');
        body = body.replace(/\\newpage/g, '');

        // Part/Chapter (for book/report)
        body = body.replace(/\\part\*?\{([^}]*)\}/g, '<h1 style="text-align:center;margin:2em 0">$1</h1>');
        body = body.replace(/\\chapter\*?\{([^}]*)\}/g, '<h2 style="page-break-before:always">$1</h2>');

        // Table of contents placeholder
        body = body.replace(/\\tableofcontents/g, '<div style="text-align:center;color:#666;padding:1em">[Оглавление]</div>');

        // Maketitle placeholder (if not caught above)
        body = body.replace(/\\maketitle/g, '');

        // New line
        body = body.replace(/\\newline/g, '<br>');

        // Horizontal rule
        body = body.replace(/\\hrulefill/g, '<hr>');
        body = body.replace(/\\hrule/g, '<hr>');

        // Today
        body = body.replace(/\\today/g, new Date().toLocaleDateString('ru'));

        // Wrap in paragraphs
        result += `<p>${body}</p>`;

        return result;
    }

    function processInlineLatex(text) {
        // Process inline math in text
        text = text.replace(/\$([^$]+?)\$/g, function(m, eq) {
            try {
                return katex.renderToString(eq.trim(), { displayMode: false, throwOnError: false });
            } catch (e) {
                return eq;
            }
        });
        text = text.replace(/\\textbf\{([^}]*)\}/g, '<strong>$1</strong>');
        text = text.replace(/\\textit\{([^}]*)\}/g, '<em>$1</em>');
        text = text.replace(/\\emph\{([^}]*)\}/g, '<em>$1</em>');
        text = text.replace(/\\underline\{([^}]*)\}/g, '<u>$1</u>');
        text = text.replace(/\\texttt\{([^}]*)\}/g, '<code style="background:#f5f5f5;padding:2px 4px;border-radius:3px;font-family:monospace">$1</code>');
        text = text.replace(/\\cite\{([^}]*)\}/g, '[$1]');
        text = text.replace(/\\ref\{([^}]*)\}/g, '→$1');
        text = text.replace(/\\label\{([^}]*)\}/g, '');
        return text;
    }

    // ==================== TOOLBAR ====================
    function insertLatex(text, cursorOffset) {
        const doc = editor.getDoc();
        const selection = doc.getSelection();
        if (selection) {
            // Check if the template has {} placeholders
            if (text.includes('{}')) {
                const newText = text.replace('{}', `{${selection}}`);
                doc.replaceSelection(newText);
            } else {
                doc.replaceSelection(text.replace(/\n/g, ''));
            }
        } else {
            doc.replaceSelection(text);
            if (cursorOffset) {
                const cursor = doc.getCursor();
                // Simple positioning - move cursor to common positions
                if (text.includes('{}')) {
                    const beforeCursor = text.substring(0, text.indexOf('{}') + 1);
                    const lineOffset = beforeCursor.split('\n').length - 1;
                    const charOffset = lineOffset > 0 ? beforeCursor.split('\n').pop().length : beforeCursor.length;
                    doc.setCursor(cursor.line - lineOffset, cursor.ch - (text.replace(/\n/g, '').length - charOffset) + 1);
                }
            }
        }
        editor.focus();
    }

    function toggleComment() {
        editor.toggleComment();
    }

    function toggleFindReplace() {
        const fr = document.getElementById('findReplace');
        fr.classList.toggle('active');
        if (fr.classList.contains('active')) {
            document.getElementById('findInput').focus();
            // Auto-fill with selection
            const selection = editor.getSelection();
            if (selection) {
                document.getElementById('findInput').value = selection;
                findInEditor();
            }
        }
    }

    function findInEditor() {
        const query = document.getElementById('findInput').value;
        if (!query) {
            document.getElementById('findCount').textContent = '0 результатов';
            return;
        }
        const cursor = editor.getSearchCursor(query);
        let count = 0;
        while (cursor.findNext()) count++;
        document.getElementById('findCount').textContent = `${count} результат${count === 1 ? '' : count < 5 ? 'а' : 'ов'}`;

        // Jump to first match
        const firstCursor = editor.getSearchCursor(query);
        if (firstCursor.findNext()) {
            editor.setSelection(firstCursor.from(), firstCursor.to());
        }
    }

    function replaceInEditor() {
        const query = document.getElementById('findInput').value;
        const replacement = document.getElementById('replaceInput').value;
        if (!query) return;

        const cursor = editor.getSearchCursor(query);
        if (cursor.findNext()) {
            cursor.replace(replacement);
            findInEditor();
        }
    }

    function replaceAllInEditor() {
        const query = document.getElementById('findInput').value;
        const replacement = document.getElementById('replaceInput').value;
        if (!query) return;

        let count = 0;
        const cursor = editor.getSearchCursor(query);
        while (cursor.findNext()) {
            cursor.replace(replacement);
            count++;
        }
        document.getElementById('findCount').textContent = `Заменено: ${count}`;
        showToast(`Заменено ${count} вхождений`, 'success');
    }

    // ==================== VIEW MODES ====================
    function setViewMode(mode) {
        const editorPane = document.getElementById('editorPane');
        const previewPane = document.getElementById('previewPane');
        const resizer = document.getElementById('resizer');

        document.querySelectorAll('.split-option').forEach(b => b.classList.remove('active'));

        switch (mode) {
            case 'split':
                editorPane.style.display = 'flex';
                previewPane.style.display = 'flex';
                resizer.style.display = 'block';
                editorPane.style.flex = '1';
                previewPane.style.flex = '1';
                document.getElementById('splitBtn').classList.add('active');
                break;
            case 'editor':
                editorPane.style.display = 'flex';
                previewPane.style.display = 'none';
                resizer.style.display = 'none';
                editorPane.style.flex = '1';
                document.getElementById('editorBtn').classList.add('active');
                break;
            case 'preview':
                editorPane.style.display = 'none';
                previewPane.style.display = 'flex';
                resizer.style.display = 'none';
                previewPane.style.flex = '1';
                document.getElementById('previewBtn').classList.add('active');
                break;
        }
        editor.refresh();
    }

    function switchPreviewTab(tab, el) {
        el.parentElement.querySelectorAll('.pane-tab').forEach(t => t.classList.remove('active'));
        el.classList.add('active');

        if (tab === 'source') {
            document.getElementById('previewContent').textContent = editor.getValue();
            document.getElementById('previewContent').style.fontFamily = "'JetBrains Mono', monospace";
            document.getElementById('previewContent').style.whiteSpace = 'pre-wrap';
            document.getElementById('previewContent').style.fontSize = '13px';
            document.getElementById('previewContent').style.lineHeight = '1.6';
        } else {
            document.getElementById('previewContent').style.fontFamily = '';
            document.getElementById('previewContent').style.whiteSpace = '';
            document.getElementById('previewContent').style.fontSize = '';
            document.getElementById('previewContent').style.lineHeight = '';
            compileLatex();
        }
    }

    // ==================== RESIZER ====================
    function initResizer() {
        const resizer = document.getElementById('resizer');
        const editorPane = document.getElementById('editorPane');
        const previewPane = document.getElementById('previewPane');
        let isResizing = false;

        resizer.addEventListener('mousedown', function(e) {
            isResizing = true;
            resizer.classList.add('active');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;
            const container = document.getElementById('editorPanes');
            const rect = container.getBoundingClientRect();
            const offset = e.clientX - rect.left;
            const total = rect.width;
            const percent = (offset / total) * 100;

            if (percent > 20 && percent < 80) {
                editorPane.style.flex = `0 0 ${percent}%`;
                previewPane.style.flex = `0 0 ${100 - percent}%`;
                editor.refresh();
            }
        });

        document.addEventListener('mouseup', function() {
            isResizing = false;
            resizer.classList.remove('active');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });
    }

    // ==================== SIDEBAR ====================
    function toggleSidebar() {
        document.getElementById('sidebar').classList.toggle('collapsed');
        setTimeout(() => editor.refresh(), 200);
    }

    function switchSidebarTab(tab, el) {
        el.parentElement.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
        el.classList.add('active');

        const tree = document.getElementById('fileTree');
        const footer = document.querySelector('.sidebar-footer');

        if (tab === 'snippets') {
            tree.innerHTML = `
                <div class="file-item" onclick="insertLatex('\\alpha', 0)"><span style="font-size:14px">α</span> <span class="file-name">\\alpha</span></div>
                <div class="file-item" onclick="insertLatex('\\beta', 0)"><span style="font-size:14px">β</span> <span class="file-name">\\beta</span></div>
                <div class="file-item" onclick="insertLatex('\\gamma', 0)"><span style="font-size:14px">γ</span> <span class="file-name">\\gamma</span></div>
                <div class="file-item" onclick="insertLatex('\\delta', 0)"><span style="font-size:14px">δ</span> <span class="file-name">\\delta</span></div>
                <div class="file-item" onclick="insertLatex('\\epsilon', 0)"><span style="font-size:14px">ε</span> <span class="file-name">\\epsilon</span></div>
                <div class="file-item" onclick="insertLatex('\\theta', 0)"><span style="font-size:14px">θ</span> <span class="file-name">\\theta</span></div>
                <div class="file-item" onclick="insertLatex('\\lambda', 0)"><span style="font-size:14px">λ</span> <span class="file-name">\\lambda</span></div>
                <div class="file-item" onclick="insertLatex('\\mu', 0)"><span style="font-size:14px">μ</span> <span class="file-name">\\mu</span></div>
                <div class="file-item" onclick="insertLatex('\\pi', 0)"><span style="font-size:14px">π</span> <span class="file-name">\\pi</span></div>
                <div class="file-item" onclick="insertLatex('\\sigma', 0)"><span style="font-size:14px">σ</span> <span class="file-name">\\sigma</span></div>
                <div class="file-item" onclick="insertLatex('\\phi', 0)"><span style="font-size:14px">φ</span> <span class="file-name">\\phi</span></div>
                <div class="file-item" onclick="insertLatex('\\omega', 0)"><span style="font-size:14px">ω</span> <span class="file-name">\\omega</span></div>
                <div class="file-item" onclick="insertLatex('\\infty', 0)"><span style="font-size:14px">∞</span> <span class="file-name">\\infty</span></div>
                <div class="file-item" onclick="insertLatex('\\partial', 0)"><span style="font-size:14px">∂</span> <span class="file-name">\\partial</span></div>
                <div class="file-item" onclick="insertLatex('\\nabla', 0)"><span style="font-size:14px">∇</span> <span class="file-name">\\nabla</span></div>
                <div class="file-item" onclick="insertLatex('\\in', 0)"><span style="font-size:14px">∈</span> <span class="file-name">\\in</span></div>
                <div class="file-item" onclick="insertLatex('\\notin', 0)"><span style="font-size:14px">∉</span> <span class="file-name">\\notin</span></div>
                <div class="file-item" onclick="insertLatex('\\subset', 0)"><span style="font-size:14px">⊂</span> <span class="file-name">\\subset</span></div>
                <div class="file-item" onclick="insertLatex('\\cup', 0)"><span style="font-size:14px">∪</span> <span class="file-name">\\cup</span></div>
                <div class="file-item" onclick="insertLatex('\\cap', 0)"><span style="font-size:14px">∩</span> <span class="file-name">\\cap</span></div>
            `;
            footer.style.display = 'none';
        } else if (tab === 'history') {
            tree.innerHTML = `
                <div class="file-item" style="cursor:default">
                    <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                    </svg>
                    <span class="file-name">Автосохранение — ${new Date().toLocaleTimeString('ru')}</span>
                </div>
            `;
            footer.style.display = 'none';
        } else {
            renderFileTree();
            footer.style.display = 'block';
        }
    }

    // ==================== AI GENERATION ====================
    function getGenerationFieldValue(id) {
        const element = document.getElementById(id);
        return element ? element.value.trim() : '';
    }

    function setGenerationStatus(message, type = '') {
        const status = document.getElementById('generationStatus');
        if (!status) return;
        status.textContent = message;
        status.className = `generation-status ${type}`.trim();
    }

    function setGenerationDetails(items = [], type = '') {
        const details = document.getElementById('generationDetails');
        if (!details) return;
        details.className = `generation-details ${type}`.trim();
        if (!items.length) {
            details.innerHTML = '';
            return;
        }
        details.innerHTML = `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
    }

    function setButtonLoading(id, isLoading, loadingText = 'Выполняется...') {
        const btn = document.getElementById(id);
        if (!btn) return;
        if (isLoading) {
            btn.dataset.originalText = btn.textContent.trim();
            btn.disabled = true;
            btn.textContent = loadingText;
        } else {
            btn.disabled = false;
            if (btn.dataset.originalText) {
                btn.textContent = btn.dataset.originalText;
            }
        }
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function updateGenerationModelDefault() {
        const provider = getGenerationFieldValue('generationProvider');
        const modelInput = document.getElementById('generationModel');
        if (!modelInput) return;
        if (provider === 'vendor' && (!modelInput.value || modelInput.value === 'qwen2.5:14b')) {
            modelInput.value = 'gpt-4o-mini';
        }
        if (provider === 'ollama' && (!modelInput.value || modelInput.value === 'gpt-4o-mini')) {
            modelInput.value = 'qwen2.5:14b';
        }
    }

    async function showGenerationModal() {
        const modal = document.getElementById('generationModal');
        modal.classList.add('active');
        setGenerationDetails();

        if (backendAvailable) {
            try {
                generationPresets = await apiRequest('/generation/presets');
                applyGenerationPreset(generationPresets[0]);
                setGenerationStatus('Поля предзаполнены. Укажите тему или материалы и запустите генерацию.');
            } catch (error) {
                setGenerationStatus(`Не удалось загрузить пресеты: ${error.message}`, 'error');
            }
        } else {
            setGenerationStatus('Backend недоступен: AI-генерация требует запущенный backend.', 'error');
        }
    }

    function applyGenerationPreset(preset) {
        if (!preset || !preset.defaults) return;
        const mapping = {
            level: 'generationLevel',
            alpha_code: 'generationAlpha',
            beta_code: 'generationBeta',
            gamma_code: 'generationGamma',
            grade: 'generationGrade',
            subject: 'generationSubject',
            priority_method: 'generationPriorityMethod',
            graph_analytic: 'generationGraphAnalytic'
        };
        Object.entries(mapping).forEach(([key, id]) => {
            const element = document.getElementById(id);
            if (element && preset.defaults[key] !== undefined) {
                element.value = preset.defaults[key];
            }
        });
    }

    function collectGenerationRequest() {
        return {
            provider: getGenerationFieldValue('generationProvider') || 'ollama',
            model: getGenerationFieldValue('generationModel') || null,
            project_id: currentProject?.id || null,
            fields: {
                level: getGenerationFieldValue('generationLevel') || 'ЕГЭ',
                alpha_code: parseInt(getGenerationFieldValue('generationAlpha') || '1', 10),
                beta_code: parseInt(getGenerationFieldValue('generationBeta') || '1', 10),
                gamma_code: parseInt(getGenerationFieldValue('generationGamma') || '4', 10),
                grade: getGenerationFieldValue('generationGrade') || '11 класс',
                student_name: getGenerationFieldValue('generationStudent'),
                subject: getGenerationFieldValue('generationSubject') || 'математика',
                topic: getGenerationFieldValue('generationTopic'),
                priority_method: getGenerationFieldValue('generationPriorityMethod') || 'нейросеть выбирает самостоятельно по отношению к уровню и классу',
                graph_analytic: getGenerationFieldValue('generationGraphAnalytic') || 'по ситуации'
            },
            materials: getGenerationFieldValue('generationMaterials')
        };
    }

    async function previewGenerationPrompt() {
        if (!backendAvailable) {
            setGenerationStatus('Backend недоступен: невозможно собрать prompt через API.', 'error');
            return;
        }

        setButtonLoading('previewPromptBtn', true, 'Собираю...');
        try {
            setGenerationDetails();
            setGenerationStatus('Собираю prompt...');
            const result = await apiRequest('/generation/prompt', {
                method: 'POST',
                body: JSON.stringify(collectGenerationRequest())
            });
            lastGenerationPrompt = result.prompt || '';
            const warnings = result.warnings || [];
            setGenerationStatus(`Prompt готов: ${lastGenerationPrompt.length} символов.`, warnings.length ? '' : 'success');
            setGenerationDetails(warnings, warnings.length ? '' : 'success');
            showToast('Prompt успешно собран backend-ом', 'success');
        } catch (error) {
            setGenerationStatus(`Ошибка prompt preview: ${error.message}`, 'error');
            setGenerationDetails([error.message], 'error');
            showToast(`Ошибка prompt preview: ${error.message}`, 'error');
        } finally {
            setButtonLoading('previewPromptBtn', false);
        }
    }

    function formatValidation(validation) {
        const errors = validation.errors?.length ? ` Ошибки: ${validation.errors.join(' ')}` : '';
        const warnings = validation.warnings?.length ? ` Предупреждения: ${validation.warnings.join(' ')}` : '';
        return `${validation.valid ? 'LaTeX прошел структурную проверку.' : 'LaTeX не прошел структурную проверку.'}${errors}${warnings}`;
    }

    function renderValidationDetails(validation) {
        const items = [];
        (validation.errors || []).forEach(error => items.push(`Ошибка: ${error}`));
        (validation.warnings || []).forEach(warning => items.push(`Предупреждение: ${warning}`));
        setGenerationDetails(items, validation.valid ? 'success' : 'error');
    }

    async function validateCurrentLatex() {
        if (!backendAvailable) {
            setGenerationStatus('Backend недоступен: проверка .tex невозможна.', 'error');
            return;
        }

        setButtonLoading('validateLatexBtn', true, 'Проверяю...');
        try {
            setGenerationStatus('Проверяю текущий .tex...');
            const validation = await apiRequest('/generation/validate', {
                method: 'POST',
                body: JSON.stringify({ latex_code: editor.getValue() })
            });
            setGenerationStatus(validation.valid ? 'LaTeX прошел проверку.' : 'LaTeX требует исправлений.', validation.valid ? 'success' : 'error');
            renderValidationDetails(validation);
            showToast(validation.valid ? 'LaTeX прошел проверку' : 'LaTeX требует исправлений', validation.valid ? 'success' : 'error');
        } catch (error) {
            setGenerationStatus(`Ошибка проверки .tex: ${error.message}`, 'error');
            setGenerationDetails([error.message], 'error');
            showToast(`Ошибка проверки .tex: ${error.message}`, 'error');
        } finally {
            setButtonLoading('validateLatexBtn', false);
        }
    }

    async function checkGenerationProvider() {
        if (!backendAvailable) {
            setGenerationStatus('Backend недоступен: проверка провайдера невозможна.', 'error');
            return;
        }

        const provider = encodeURIComponent(getGenerationFieldValue('generationProvider') || 'ollama');
        const model = encodeURIComponent(getGenerationFieldValue('generationModel'));
        const suffix = model ? `&model=${model}` : '';
        setButtonLoading('checkProviderBtn', true, 'Проверяю...');
        try {
            setGenerationDetails();
            setGenerationStatus('Проверяю AI-provider...');
            const status = await apiRequest(`/generation/providers/status?provider=${provider}${suffix}`);
            const modelInfo = status.model_available === false ? ' Модель не найдена.' : '';
            const details = [
                `Провайдер: ${status.provider}`,
                `Модель: ${status.model}`,
                `Доступен: ${status.available ? 'да' : 'нет'}`,
                `Модель доступна: ${status.model_available === null ? 'неизвестно' : (status.model_available ? 'да' : 'нет')}`
            ];
            setGenerationStatus(`${status.message}${modelInfo}`, status.available ? 'success' : 'error');
            setGenerationDetails(details, status.available ? 'success' : 'error');
            showToast(status.available ? 'AI-provider доступен' : 'AI-provider недоступен', status.available ? 'success' : 'error');
        } catch (error) {
            setGenerationStatus(`Ошибка проверки провайдера: ${error.message}`, 'error');
            setGenerationDetails([error.message], 'error');
            showToast(`Ошибка проверки провайдера: ${error.message}`, 'error');
        } finally {
            setButtonLoading('checkProviderBtn', false);
        }
    }

    function getGenerationInsertMode() {
        return getGenerationFieldValue('generationInsertMode') || 'new';
    }

    function ensureTexFilename(name) {
        const fallback = 'generated.tex';
        const cleaned = (name || fallback).trim().replace(/[\\/]/g, '_');
        return cleaned.endsWith('.tex') ? cleaned : `${cleaned}.tex`;
    }

    function uniqueFileName(baseName) {
        const safeName = ensureTexFilename(baseName);
        const existingNames = new Set(Object.values(files).map(file => file.name));
        if (!existingNames.has(safeName)) return safeName;
        const stem = safeName.replace(/\.tex$/i, '');
        let index = 2;
        let candidate = `${stem}_${index}.tex`;
        while (existingNames.has(candidate)) {
            index += 1;
            candidate = `${stem}_${index}.tex`;
        }
        return candidate;
    }

    async function createFileWithContent(name, content) {
        const filename = uniqueFileName(name);
        if (backendAvailable && currentProject) {
            const file = await apiRequest(`/files/project/${currentProject.id}`, {
                method: 'POST',
                body: JSON.stringify({ name: filename, content, is_main: false })
            });
            files[file.id] = file;
            await switchFile(file.id);
            return file;
        }

        const id = 'file_' + Date.now();
        files[id] = { id, name: filename, content, is_main: false };
        await switchFile(id);
        return files[id];
    }

    async function applyGeneratedLatex(latexCode) {
        const mode = getGenerationInsertMode();
        const currentName = files[currentFileId]?.name || 'текущий файл';

        if (mode === 'replace') {
            if (!confirm(`Заменить содержимое файла "${currentName}" сгенерированным LaTeX?`)) {
                setGenerationStatus('Вставка отменена пользователем.');
                return false;
            }
            suppressEditorChange = true;
            editor.setValue(latexCode);
            suppressEditorChange = false;
            files[currentFileId].content = latexCode;
            updateWordCount();
            await saveCurrentFile();
            return true;
        }

        if (mode === 'append') {
            const separator = editor.getValue().trim() ? '\n\n' : '';
            suppressEditorChange = true;
            editor.setValue(`${editor.getValue()}${separator}${latexCode}`);
            suppressEditorChange = false;
            files[currentFileId].content = editor.getValue();
            updateWordCount();
            await saveCurrentFile();
            return true;
        }

        await createFileWithContent(getGenerationFieldValue('generationFilename'), latexCode);
        updateWordCount();
        return true;
    }

    async function copyTextToClipboard(text, successMessage, emptyMessage) {
        if (!text) {
            showToast(emptyMessage, 'error');
            return;
        }
        try {
            await navigator.clipboard.writeText(text);
            showToast(successMessage, 'success');
        } catch (error) {
            showToast(`Не удалось скопировать: ${error.message}`, 'error');
        }
    }

    async function copyGenerationPrompt() {
        await copyTextToClipboard(lastGenerationPrompt, 'Prompt скопирован', 'Сначала выполните «Проверить prompt»');
    }

    async function copyGenerationRawOutput() {
        await copyTextToClipboard(lastGenerationRawOutput, 'Raw output скопирован', 'Raw output появится после генерации');
    }

    async function generateLatexFromAi() {
        if (!backendAvailable) {
            setGenerationStatus('Backend недоступен: AI-генерация невозможна.', 'error');
            showToast('Запустите backend для AI-генерации', 'error');
            return;
        }

        const btn = document.getElementById('generateLatexBtn');
        const previousContent = editor.getValue();
        const previousFileId = currentFileId;
        setButtonLoading('generateLatexBtn', true, 'Генерация...');
        setGenerationStatus('Генерация LaTeX через AI-provider...');
        setGenerationDetails();
        document.getElementById('statusText').textContent = 'AI-генерация...';

        try {
            await saveCurrentFile();
            const result = await apiRequest('/generation/generate', {
                method: 'POST',
                body: JSON.stringify(collectGenerationRequest())
            });
            lastGenerationRawOutput = result.raw_output || '';

            if (!result.latex_code || !result.latex_code.includes('\\documentclass')) {
                throw new Error('Модель не вернула компилируемый LaTeX от \\documentclass');
            }
            if (result.validation) {
                renderValidationDetails(result.validation);
            }
            if (result.validation && !result.validation.valid) {
                throw new Error(formatValidation(result.validation));
            }
            if (result.validation?.warnings?.length) {
                setGenerationStatus(formatValidation(result.validation));
            }

            const applied = await applyGeneratedLatex(result.latex_code);
            if (!applied) return;

            closeModal('generationModal');
            showToast(`LaTeX сгенерирован (${result.provider}/${result.model || 'default'})`, 'success');
            document.getElementById('statusText').textContent = 'AI-документ вставлен';
            compileLatex();
        } catch (error) {
            if (getGenerationInsertMode() !== 'new' && files[previousFileId]) {
                currentFileId = previousFileId;
                suppressEditorChange = true;
                editor.setValue(previousContent);
                suppressEditorChange = false;
                files[currentFileId].content = previousContent;
                renderFileTree();
            }
            setGenerationStatus(`Ошибка генерации: ${error.message}`, 'error');
            setGenerationDetails([error.message], 'error');
            document.getElementById('statusText').textContent = 'Ошибка AI-генерации';
            showToast(`Ошибка AI-генерации: ${error.message}`, 'error');
        } finally {
            setButtonLoading('generateLatexBtn', false);
        }
    }

    // ==================== TEMPLATES ====================
    async function showTemplates() {
        const grid = document.getElementById('templateGrid');
        if (backendAvailable) {
            try {
                await loadTemplates();
            } catch (error) {
                showToast(`Ошибка загрузки шаблонов: ${error.message}`, 'error');
            }
        }
        grid.innerHTML = templates.map((t, i) => `
            <div class="template-card" onclick="applyTemplate(${i})">
                <h4>${t.name}</h4>
                <p>${t.description || t.desc || ''}</p>
            </div>
        `).join('');
        document.getElementById('templateModal').classList.add('active');
    }

    function applyTemplate(index) {
        const template = templates[index];
        editor.setValue(template.content);
        files[currentFileId].content = template.content;
        scheduleSaveCurrentFile();
        closeModal('templateModal');
        compileLatex();
        showToast(`Шаблон "${template.name}" применён`, 'success');
    }

    // ==================== EXPORT ====================
    function toggleExportMenu() {
        document.getElementById('exportMenu').classList.toggle('active');
    }

    async function exportPDF() {
        document.getElementById('exportMenu').classList.remove('active');
        if (backendAvailable && currentProject) {
            try {
                await saveCurrentFile();
                const result = await apiRequest('/export/pdf', {
                    method: 'POST',
                    body: JSON.stringify({ project_id: currentProject.id, format: 'pdf', content: collectFilesByName() })
                });
                window.open(resolveApiUrl(result.url), '_blank');
                showToast('PDF экспортирован', 'success');
                return;
            } catch (error) {
                showToast(`Ошибка PDF экспорта: ${error.message}`, 'error');
            }
        }

        const element = document.getElementById('previewContent');
        const opt = {
            margin: 10,
            filename: document.getElementById('projectNameInput').value + '.pdf',
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2 },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };
        showToast('Генерация PDF...', 'info');
        html2pdf().set(opt).from(element).save().then(() => {
            showToast('PDF сохранён локально', 'success');
        });
    }

    async function exportHTML() {
        document.getElementById('exportMenu').classList.remove('active');
        if (backendAvailable && currentProject) {
            try {
                await saveCurrentFile();
                const result = await apiRequest('/export/html', {
                    method: 'POST',
                    body: JSON.stringify({ project_id: currentProject.id, format: 'html', content: collectFilesByName() })
                });
                window.open(resolveApiUrl(result.url), '_blank');
                showToast('HTML экспортирован', 'success');
                return;
            } catch (error) {
                showToast(`Ошибка HTML экспорта: ${error.message}`, 'error');
            }
        }

        const content = document.getElementById('previewContent').innerHTML;
        const html = `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${document.getElementById('projectNameInput').value}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"><\/script>
<style>
body { font-family: Georgia, serif; max-width: 700px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #000; }
h1 { text-align: center; font-size: 2em; }
h2 { font-size: 1.5em; margin-top: 1.5em; }
h3 { font-size: 1.25em; margin-top: 1em; }
.equation-block { text-align: center; margin: 1.5em 0; }
.abstract { margin: 1em 2em; font-style: italic; }
.author { text-align: center; font-size: 1.1em; }
.date { text-align: center; color: #555; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
td, th { border: 1px solid #ccc; padding: 8px 12px; text-align: center; }
th { background: #f5f5f5; }
</style>
</head>
<body>
${content}
</body>
</html>`;
        downloadFile(html, document.getElementById('projectNameInput').value + '.html', 'text/html');
        showToast('HTML сохранён локально', 'success');
    }

    async function exportLatex() {
        document.getElementById('exportMenu').classList.remove('active');
        if (backendAvailable && currentProject) {
            try {
                await saveCurrentFile();
                const result = await apiRequest('/export/tex', {
                    method: 'POST',
                    body: JSON.stringify({ project_id: currentProject.id, format: 'tex', content: collectFilesByName() })
                });
                window.open(resolveApiUrl(result.url), '_blank');
                showToast('TEX архив экспортирован', 'success');
                return;
            } catch (error) {
                showToast(`Ошибка TEX экспорта: ${error.message}`, 'error');
            }
        }
        downloadFile(editor.getValue(), document.getElementById('projectNameInput').value + '.tex', 'text/plain');
        showToast('LaTeX файл сохранён локально', 'success');
    }

    function downloadFile(content, filename, type) {
        const blob = new Blob([content], { type: type + ';charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }

    async function saveFile() {
        try {
            await saveCurrentFile();
            showToast('Файл сохранён', 'success');
        } catch (error) {
            showToast(`Ошибка сохранения файла: ${error.message}`, 'error');
        }
    }

    // ==================== MODALS ====================
    function closeModal(id) {
        document.getElementById(id).classList.remove('active');
    }

    function toggleSettings() {
        document.getElementById('settingsModal').classList.add('active');
    }

    function editProjectName() {
        document.getElementById('projectNameInput').select();
    }

    async function saveProjectName() {
        const input = document.getElementById('projectNameInput');
        const name = input.value.trim();
        if (!name) return;

        if (!backendAvailable || !currentProject) {
            showToast('Название обновлено локально', 'info');
            return;
        }

        try {
            currentProject = await apiRequest(`/projects/${currentProject.id}`, {
                method: 'PUT',
                body: JSON.stringify({ name })
            });
            input.value = currentProject.name;
            showToast('Название проекта сохранено', 'success');
        } catch (error) {
            showToast(`Ошибка сохранения проекта: ${error.message}`, 'error');
        }
    }

    // ==================== COMMAND PALETTE ====================
    function toggleCommandPalette() {
        const palette = document.getElementById('commandPalette');
        palette.classList.toggle('active');
        if (palette.classList.contains('active')) {
            document.getElementById('commandInput').value = '';
            document.getElementById('commandInput').focus();
            renderCommands(commands);
            selectedCommandIndex = 0;
        }
    }

    function filterCommands(query) {
        const filtered = commands.filter(c =>
            c.name.toLowerCase().includes(query.toLowerCase())
        );
        renderCommands(filtered);
        selectedCommandIndex = 0;
        updateCommandSelection();
    }

    function renderCommands(cmds) {
        const list = document.getElementById('commandList');
        list.innerHTML = cmds.map((c, i) => `
            <div class="command-item ${i === 0 ? 'selected' : ''}" onclick="executeCommand(${commands.indexOf(c)})" data-index="${i}">
                <span>${c.name}</span>
                ${c.shortcut ? `<span class="shortcut">${c.shortcut}</span>` : ''}
            </div>
        `).join('');
    }

    function updateCommandSelection() {
        document.querySelectorAll('.command-item').forEach((item, i) => {
            item.classList.toggle('selected', i === selectedCommandIndex);
        });
    }

    function executeCommand(index) {
        if (commands[index]) {
            commands[index].action();
            document.getElementById('commandPalette').classList.remove('active');
        }
    }

    document.getElementById('commandInput').addEventListener('keydown', function(e) {
        const items = document.querySelectorAll('.command-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedCommandIndex = (selectedCommandIndex + 1) % items.length;
            updateCommandSelection();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedCommandIndex = (selectedCommandIndex - 1 + items.length) % items.length;
            updateCommandSelection();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const selected = document.querySelector('.command-item.selected');
            if (selected) selected.click();
        }
    });

    // ==================== SETTINGS ====================
    function changeEditorTheme(theme) {
        editor.setOption('theme', theme);
    }

    function changeFontSize(size) {
        editor.getWrapperElement().style.fontSize = size + 'px';
        editor.refresh();
    }

    function toggleWordWrap(el) {
        el.classList.toggle('active');
        editor.setOption('lineWrapping', el.classList.contains('active'));
    }

    function toggleLineNumbers(el) {
        el.classList.toggle('active');
        editor.setOption('lineNumbers', el.classList.contains('active'));
    }

    function toggleAutoCompile(el) {
        el.classList.toggle('active');
        autoCompile = el.classList.contains('active');
        showToast(autoCompile ? 'Автокомпиляция включена' : 'Автокомпиляция выключена', 'info');
    }

    function toggleTheme() {
        const current = editor.getOption('theme');
        editor.setOption('theme', current === 'monokai' ? 'idea' : 'monokai');
        document.getElementById('editorTheme').value = current === 'monokai' ? 'idea' : 'monokai';
    }

    function toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }

    // ==================== UTILITIES ====================
    function updateWordCount() {
        const text = editor.getValue();
        const words = text.trim().split(/\s+/).filter(w => w.length > 0).length;
        const chars = text.length;
        document.getElementById('wordCount').textContent = `${words} слов, ${chars} символов`;
    }

    function showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
        };

        toast.innerHTML = `${icons[type] || icons.info}<span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // ==================== INIT ====================
    window.addEventListener('DOMContentLoaded', init);
