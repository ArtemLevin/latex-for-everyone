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

            const name = document.createElement('span');
            name.className = 'file-name';
            name.textContent = file.name;

            const actions = document.createElement('div');
            actions.className = 'file-actions';

            const renameButton = document.createElement('button');
            renameButton.className = 'file-action-btn';
            renameButton.type = 'button';
            renameButton.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
            renameButton.addEventListener('click', function(event) {
                event.stopPropagation();
                renameFile(id);
            });

            const deleteButton = document.createElement('button');
            deleteButton.className = 'file-action-btn delete';
            deleteButton.type = 'button';
            deleteButton.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
            deleteButton.addEventListener('click', function(event) {
                event.stopPropagation();
                deleteFile(id);
            });

            actions.appendChild(renameButton);
            actions.appendChild(deleteButton);
            item.insertAdjacentHTML('beforeend', icon);
            item.appendChild(name);
            item.appendChild(actions);
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

    // ==================== DOCUMENT INSIGHT ====================
    function escapeInsightHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function formatInsightDate(value) {
        if (!value) return '—';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '—';
        return date.toLocaleString('ru-RU');
    }

    function getInsightTokenUsage(meta) {
        const tokenUsage = meta?.token_usage || {};
        const input = tokenUsage.input_tokens ?? meta?.input_tokens ?? 0;
        const output = tokenUsage.output_tokens ?? meta?.output_tokens ?? 0;
        const total = tokenUsage.total_tokens ?? meta?.total_tokens ?? (input + output);
        const source = tokenUsage.source || meta?.token_count_source || 'estimated';
        return { input, output, total, source };
    }

    function getInsightAiRuns(meta) {
        if (meta?.ai_runs) return meta.ai_runs;
        const compileCheck = meta?.compile_check || {};
        if (!compileCheck.repaired) return 1;
        return 1 + Math.max((compileCheck.attempts || 1) - 1, 1);
    }

    function historyItemToInsightMeta(item) {
        if (!item) return null;
        return {
            prompt: item.prompt_preview || '',
            prompt_hash: item.prompt_hash || '',
            provider: item.provider || '—',
            model: item.model || '—',
            status: item.status || '—',
            topic: item.fields?.topic || '',
            subject: item.fields?.subject || '',
            language: item.fields?.language || '',
            latex_mode: item.fields?.latex_mode || '',
            content_source_mode: item.fields?.content_source_mode || '',
            validation: item.validation || null,
            compile_check: item.compile_check || null,
            input_tokens: item.input_tokens || 0,
            output_tokens: item.output_tokens || 0,
            total_tokens: item.total_tokens || 0,
            token_count_source: item.token_count_source || 'estimated',
            latex_code_hash: item.latex_code_hash || '',
            created_at: item.created_at || null,
            history_id: item.id || ''
        };
    }

    async function loadLatestGenerationInsight() {
        if (!backendAvailable || !currentProject) return null;
        const history = await apiRequest(`/generation/history/project/${currentProject.id}?limit=1`);
        return historyItemToInsightMeta(history[0]);
    }

    function renderDocumentInsight(file, meta, sourceLabel) {
        const status = document.getElementById('documentInsightStatus');
        const stats = document.getElementById('documentInsightStats');
        const promptBox = document.getElementById('documentInsightPrompt');
        const details = document.getElementById('documentInsightMeta');
        const tokenUsage = getInsightTokenUsage(meta);
        const validation = meta?.validation || {};
        const compileCheck = meta?.compile_check || {};
        const promptText = meta?.prompt || 'Prompt не найден. Для старых/загруженных файлов доступно только сохранённое превью из generation history.';
        const aiRuns = getInsightAiRuns(meta);

        status.textContent = meta
            ? `Исследование «${file.name}»: ${sourceLabel}.`
            : `Для «${file.name}» нет AI-метаданных в текущей сессии и generation history.`;
        stats.innerHTML = [
            ['AI-прогоны', aiRuns],
            ['Токены всего', tokenUsage.total],
            ['Вход / выход', `${tokenUsage.input} / ${tokenUsage.output}`],
            ['Источник', tokenUsage.source === 'estimated' ? 'оценка' : tokenUsage.source]
        ].map(([label, value]) => `<div class="document-insight-card"><span>${escapeInsightHtml(label)}</span><strong>${escapeInsightHtml(value)}</strong></div>`).join('');
        promptBox.value = promptText;

        const rows = [];
        rows.push(`Провайдер/модель: ${meta?.provider || '—'} / ${meta?.model || '—'}`);
        rows.push(`Тема: ${meta?.topic || '—'}; предмет: ${meta?.subject || '—'}; язык: ${meta?.language || '—'}`);
        rows.push(`Режимы: content_source=${meta?.content_source_mode || '—'}, latex_mode=${meta?.latex_mode || '—'}`);
        rows.push(`Validation: ${validation.valid === undefined ? 'нет данных' : (validation.valid ? 'ok' : 'ошибки')}; warnings=${(validation.warnings || []).length}; errors=${(validation.errors || []).length}`);
        rows.push(`Compile-check: ${compileCheck.attempted ? (compileCheck.success ? 'success' : 'failed') : (compileCheck.skipped_reason || 'не запускался')}; repaired=${compileCheck.repaired ? 'yes' : 'no'}; attempts=${compileCheck.attempts || 0}`);
        rows.push(`Создано: ${formatInsightDate(meta?.created_at)}; prompt_hash=${meta?.prompt_hash || '—'}; latex_hash=${meta?.latex_code_hash || '—'}`);
        details.innerHTML = `<ul>${rows.map(row => `<li>${escapeInsightHtml(row)}</li>`).join('')}</ul>`;
    }

    function openDocumentInsightModal(file) {
        const modal = document.getElementById('documentInsightModal');
        const status = document.getElementById('documentInsightStatus');
        const stats = document.getElementById('documentInsightStats');
        const promptBox = document.getElementById('documentInsightPrompt');
        const metaBox = document.getElementById('documentInsightMeta');
        if (!modal || !status || !stats || !promptBox || !metaBox) {
            showToast('Окно исследования AI-документа не найдено в DOM', 'error');
            return false;
        }
        modal.classList.add('active');
        status.textContent = `Ищу AI-следы для «${file.name}»...`;
        stats.innerHTML = '<div class="document-insight-card"><span>Статус</span><strong>Загрузка...</strong></div>';
        promptBox.value = '';
        metaBox.innerHTML = '';
        return true;
    }

    async function inspectContextDocument(fileId = contextMenuFileId) {
        const file = files[fileId];
        if (!file) {
            showToast('Файл для исследования не найден', 'error');
            return;
        }
        if (!openDocumentInsightModal(file)) return;

        try {
            const meta = file.generationMeta || await loadLatestGenerationInsight();
            renderDocumentInsight(file, meta, file.generationMeta ? 'метаданные текущей сессии' : 'последняя запись generation history проекта');
        } catch (error) {
            renderDocumentInsight(file, file.generationMeta || null, 'локальные метаданные');
            showToast(`Не удалось загрузить generation history: ${error.message}`, 'error');
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
            case 'inspect':
                await inspectContextDocument(contextMenuFileId);
                break;
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
