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
