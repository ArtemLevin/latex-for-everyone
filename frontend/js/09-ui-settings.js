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
