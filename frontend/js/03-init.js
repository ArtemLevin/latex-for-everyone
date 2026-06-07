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
                closeModal('documentInsightModal');
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
