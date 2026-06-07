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

        setPreviewPdfMode(false);

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
