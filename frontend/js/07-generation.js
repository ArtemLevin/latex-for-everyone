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
        if (provider === 'vendor' && (!modelInput.value || modelInput.value === 'gemma4')) {
            modelInput.value = 'gpt-4o-mini';
        }
        if (provider === 'ollama' && (!modelInput.value || modelInput.value === 'gpt-4o-mini')) {
            modelInput.value = 'gemma4';
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
            language: 'generationLanguage',
            content_source_mode: 'generationContentSourceMode',
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
                language: getGenerationFieldValue('generationLanguage') || 'русский',
                content_source_mode: getGenerationFieldValue('generationContentSourceMode') || 'materials_only',
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
