    // ==================== AI GENERATION ====================
    const GENERATION_MATERIALS_MAX_CHARS = 20000;

    function getGenerationFieldValue(id) {
        const element = document.getElementById(id);
        return element ? element.value.trim() : '';
    }

    function getGenerationRawFieldValue(id) {
        const element = document.getElementById(id);
        return element ? element.value : '';
    }

    function normalizeGenerationMaterialsForRequest(materials) {
        // Keep user-authored line breaks, but make pasted CRLF/CR text match backend normalization.
        return String(materials || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
    }

    function updateGenerationMaterialsDiagnostics() {
        const hint = document.getElementById('generationMaterialsHint');
        if (!hint) return true;
        const materials = normalizeGenerationMaterialsForRequest(getGenerationRawFieldValue('generationMaterials'));
        const remaining = GENERATION_MATERIALS_MAX_CHARS - materials.length;
        const lines = materials ? materials.split('\n').length : 0;
        hint.textContent = `Материалы: ${materials.length}/${GENERATION_MATERIALS_MAX_CHARS} символов, строк: ${lines}.`;
        hint.classList.toggle('error', remaining < 0);
        return remaining >= 0;
    }

    function validateGenerationMaterialsBeforeSubmit() {
        if (updateGenerationMaterialsDiagnostics()) return true;
        const message = `Материалы слишком большие: максимум ${GENERATION_MATERIALS_MAX_CHARS} символов.`;
        setGenerationStatus(message, 'error');
        setGenerationDetails([message], 'error');
        showToast(message, 'error');
        return false;
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

    const GENERATION_ACTION_BUTTON_IDS = [
        'previewPromptBtn',
        'checkProviderBtn',
        'validateLatexBtn',
        'retryGenerationBtn',
        'regenerateSafeBtn',
        'regenerateRichBtn',
        'insertLastGeneratedBtn',
        'generateLatexBtn'
    ];

    function setGenerationActionButtonsDisabled(isDisabled, activeButtonId = '') {
        GENERATION_ACTION_BUTTON_IDS.forEach(id => {
            const button = document.getElementById(id);
            if (!button || id === activeButtonId) return;
            button.disabled = isDisabled;
        });
    }

    function setButtonLoading(id, isLoading, loadingText = 'Выполняется...') {
        const btn = document.getElementById(id);
        if (!btn) return;
        if (isLoading) {
            if (!btn.dataset.originalText) {
                btn.dataset.originalText = btn.textContent.trim();
            }
            btn.disabled = true;
            btn.textContent = loadingText;
        } else {
            btn.disabled = false;
            if (btn.dataset.originalText) {
                btn.textContent = btn.dataset.originalText;
            }
        }
    }

    function startGenerationFunWait() {
        const messages = [
            '🧙‍♂️ Разогреваю LaTeX-котёл и приручаю формулы...',
            '🦄 Запрягаю TeX-единорога: он несёт преамбулу без ошибок...',
            '🧩 Собираю задачи, ответы и аккуратные блоки в одно пособие...',
            '🔬 Прогоняю sanity-check: скобки, окружения, math-mode...',
            '🚀 Почти готово: полирую PDF-магнитные поля и токены...'
        ];
        const facts = [
            'Safe-режим специально упрощает рискованные таблицы и графику.',
            'Если compile-check споткнётся, backend попробует один repair-прогон.',
            'Prompt и raw output не пишутся целиком в history — только безопасные превью и хэши.',
            'Токены считаются отдельно для входа и выхода генерации.',
            'После успеха PDF не компилируется сам: вы контролируете момент сборки.'
        ];
        stopGenerationFunWait();
        generationFunStep = 0;
        const renderStep = () => {
            const index = generationFunStep % messages.length;
            setGenerationStatus(messages[index]);
            setGenerationDetails([`Шаг ${generationFunStep + 1}: ${facts[index]}`]);
            generationFunStep += 1;
        };
        renderStep();
        generationFunTimer = window.setInterval(renderStep, 1800);
    }

    function stopGenerationFunWait() {
        if (generationFunTimer) {
            window.clearInterval(generationFunTimer);
            generationFunTimer = null;
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
        if (provider === 'vendor' && (!modelInput.value || modelInput.value === 'qwen2.5:3b')) {
            modelInput.value = 'gpt-4o-mini';
        }
        if (provider === 'ollama' && (!modelInput.value || modelInput.value === 'gpt-4o-mini')) {
            modelInput.value = 'qwen2.5:3b';
        }
    }

    async function showGenerationModal() {
        const modal = document.getElementById('generationModal');
        modal.classList.add('active');
        setGenerationDetails();
        setGenerationRetryActionsVisible(false);
        updateGenerationMaterialsDiagnostics();

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
            latex_mode: 'generationLatexMode',
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
                latex_mode: getGenerationFieldValue('generationLatexMode') || 'safe',
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
            materials: normalizeGenerationMaterialsForRequest(getGenerationRawFieldValue('generationMaterials'))
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

    function setGenerationRetryActionsVisible(visible, allowInsert = false) {
        ['retryGenerationBtn', 'regenerateSafeBtn', 'regenerateRichBtn'].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.style.display = visible ? '' : 'none';
        });
        const insertButton = document.getElementById('insertLastGeneratedBtn');
        if (insertButton) insertButton.style.display = visible && allowInsert ? '' : 'none';
    }

    function cloneGenerationRequest(request) {
        return JSON.parse(JSON.stringify(request));
    }

    function describeCompileCheck(compileCheck) {
        if (!compileCheck) return [];
        if (compileCheck.skipped_reason) {
            return [`Compile-check пропущен: ${compileCheck.skipped_reason}`];
        }
        if (!compileCheck.attempted) {
            return ['Compile-check не запускался.'];
        }
        const attempts = compileCheck.attempts || 0;
        if (compileCheck.success) {
            const repairInfo = compileCheck.repaired ? ' после автоматического repair' : '';
            return [`Compile-check пройден${repairInfo}. Попыток: ${attempts}.`];
        }
        const details = [`Compile-check не пройден. Попыток: ${attempts}.`];
        if (compileCheck.error) details.push(`Ошибка компиляции: ${compileCheck.error}`);
        return details;
    }

    function describeTokenUsage(tokenUsage) {
        if (!tokenUsage) return [];
        const input = tokenUsage.input_tokens ?? 0;
        const output = tokenUsage.output_tokens ?? 0;
        const total = tokenUsage.total_tokens ?? (input + output);
        const source = tokenUsage.source === 'estimated' ? 'оценка' : tokenUsage.source;
        return [`Токены за генерацию: вход ${input}, выход ${output}, всего ${total} (${source}).`];
    }

    function buildGenerationDetails(result) {
        const items = [];
        if (result?.validation) {
            (result.validation.errors || []).forEach(error => items.push(`Ошибка структуры: ${error}`));
            (result.validation.warnings || []).forEach(warning => items.push(`Предупреждение структуры: ${warning}`));
            if (result.validation.valid && !(result.validation.errors || []).length && !(result.validation.warnings || []).length) {
                items.push('Структурная проверка LaTeX пройдена.');
            }
        }
        describeCompileCheck(result?.compile_check).forEach(item => items.push(item));
        describeTokenUsage(result?.token_usage).forEach(item => items.push(item));
        return items;
    }

    function renderGenerationResultDetails(result) {
        const validationFailed = result?.validation && !result.validation.valid;
        const compileFailed = result?.compile_check?.attempted && !result.compile_check.success;
        const type = validationFailed || compileFailed ? 'error' : 'success';
        setGenerationDetails(buildGenerationDetails(result), type);
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

    async function createFileWithContent(name, content, generationMeta = null) {
        const filename = uniqueFileName(name);
        if (backendAvailable && currentProject) {
            const file = await apiRequest(`/files/project/${currentProject.id}`, {
                method: 'POST',
                body: JSON.stringify({ name: filename, content, is_main: false })
            });
            if (generationMeta) file.generationMeta = generationMeta;
            files[file.id] = file;
            await switchFile(file.id);
            return file;
        }

        const id = 'file_' + Date.now();
        files[id] = { id, name: filename, content, is_main: false, generationMeta };
        await switchFile(id);
        return files[id];
    }

    function getGenerationRunCountFromMeta(meta) {
        const compileCheck = meta?.compile_check || {};
        if (!compileCheck.repaired) return 1;
        return 1 + Math.max((compileCheck.attempts || 1) - 1, 1);
    }

    function buildGenerationMeta(result) {
        const fields = lastGenerationRequest?.fields || {};
        const tokenUsage = result.token_usage || {};
        const meta = {
            prompt: result.prompt || '',
            provider: result.provider || 'default',
            model: result.model || 'default',
            status: result.status || 'success',
            topic: fields.topic || '',
            subject: fields.subject || '',
            language: fields.language || '',
            latex_mode: fields.latex_mode || '',
            content_source_mode: fields.content_source_mode || '',
            validation: result.validation || null,
            compile_check: result.compile_check || null,
            token_usage: tokenUsage,
            created_at: new Date().toISOString()
        };
        meta.ai_runs = getGenerationRunCountFromMeta(meta);
        meta.total_tokens = tokenUsage.total_tokens ?? ((tokenUsage.input_tokens || 0) + (tokenUsage.output_tokens || 0));
        return meta;
    }

    async function applyGeneratedLatex(latexCode, generationMeta = null) {
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
            if (generationMeta) files[currentFileId].generationMeta = generationMeta;
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
            if (generationMeta) files[currentFileId].generationMeta = generationMeta;
            updateWordCount();
            await saveCurrentFile();
            return true;
        }

        await createFileWithContent(getGenerationFieldValue('generationFilename'), latexCode, generationMeta);
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

    function generationNeedsUserDecision(result) {
        if (result?.validation && !result.validation.valid) return true;
        return Boolean(result?.compile_check?.attempted && !result.compile_check.success);
    }

    async function insertLastGeneratedLatex() {
        if (!lastGenerationResult?.latex_code) {
            setGenerationStatus('Нет последнего результата для вставки.', 'error');
            showToast('Сначала выполните AI-генерацию', 'error');
            return;
        }

        const applied = await applyGeneratedLatex(lastGenerationResult.latex_code, buildGenerationMeta(lastGenerationResult));
        if (!applied) return;

        closeModal('generationModal');
        showToast('LaTeX вставлен для ручной правки', 'success');
        document.getElementById('statusText').textContent = 'AI-документ вставлен для ручной правки';
    }

    function formatApiError(error) {
        if (error.status === 429) {
            const retryAfter = Number(error.retryAfter || 0);
            const suffix = retryAfter > 0 ? ` Подождите примерно ${retryAfter} сек. и повторите.` : ' Подождите немного и повторите.';
            return `${error.message}${suffix}`;
        }
        return error.message;
    }

    async function runGenerationRequest(request, loadingButtonId = 'generateLatexBtn') {
        if (!backendAvailable) {
            setGenerationStatus('Backend недоступен: AI-генерация невозможна.', 'error');
            showToast('Запустите backend для AI-генерации', 'error');
            return;
        }
        if (!validateGenerationMaterialsBeforeSubmit()) {
            return;
        }
        if (generationRequestInFlight) {
            setGenerationStatus('AI-генерация уже выполняется. Дождитесь завершения текущего запроса.', 'error');
            showToast('AI-генерация уже выполняется', 'error');
            return;
        }
        const waitMs = generationRateLimitedUntil - Date.now();
        if (waitMs > 0) {
            const waitSeconds = Math.ceil(waitMs / 1000);
            const message = `AI-генерация временно ограничена rate limit. Подождите примерно ${waitSeconds} сек.`;
            setGenerationStatus(message, 'error');
            setGenerationDetails([message], 'error');
            showToast(message, 'error');
            return;
        }

        generationRequestInFlight = true;
        const previousContent = editor.getValue();
        const previousFileId = currentFileId;
        setGenerationActionButtonsDisabled(true, loadingButtonId);
        setButtonLoading(loadingButtonId, true, 'Генерация...');
        setGenerationRetryActionsVisible(false);
        startGenerationFunWait();
        document.getElementById('statusText').textContent = 'AI-генерация — творим чудо...';

        try {
            await saveCurrentFile();
            lastGenerationRequest = cloneGenerationRequest(request);
            const result = await apiRequest('/generation/generate', {
                method: 'POST',
                body: JSON.stringify(request)
            });
            stopGenerationFunWait();
            lastGenerationResult = result;
            lastGenerationRawOutput = result.raw_output || '';

            if (!result.latex_code || !result.latex_code.includes('\\documentclass')) {
                throw new Error('Модель не вернула компилируемый LaTeX от \\documentclass');
            }

            renderGenerationResultDetails(result);

            if (generationNeedsUserDecision(result)) {
                const reason = result.validation && !result.validation.valid
                    ? formatValidation(result.validation)
                    : 'Compile-check не прошёл: можно повторить repair, перегенерировать в safe/rich режиме или вставить результат вручную.';
                setGenerationStatus(reason, 'error');
                setGenerationRetryActionsVisible(true, Boolean(result.latex_code));
                document.getElementById('statusText').textContent = 'AI-генерация требует проверки';
                showToast('AI-результат требует repair/retry перед вставкой', 'error');
                return;
            }

            if (result.validation?.warnings?.length) {
                setGenerationStatus(formatValidation(result.validation));
            }

            const applied = await applyGeneratedLatex(result.latex_code, buildGenerationMeta(result));
            if (!applied) return;

            closeModal('generationModal');
            showToast(`LaTeX сгенерирован (${result.provider}/${result.model || 'default'})`, 'success');
            document.getElementById('statusText').textContent = 'AI-документ вставлен';
            compileLatex();
        } catch (error) {
            stopGenerationFunWait();
            if (getGenerationInsertMode() !== 'new' && files[previousFileId]) {
                currentFileId = previousFileId;
                suppressEditorChange = true;
                editor.setValue(previousContent);
                suppressEditorChange = false;
                files[currentFileId].content = previousContent;
                renderFileTree();
            }
            if (error.status === 429) {
                const retryAfter = Number(error.retryAfter || 0);
                generationRateLimitedUntil = retryAfter > 0 ? Date.now() + retryAfter * 1000 : Date.now() + 60_000;
            }
            const message = formatApiError(error);
            setGenerationRetryActionsVisible(Boolean(lastGenerationRequest), Boolean(lastGenerationResult?.latex_code));
            setGenerationStatus(`Ошибка генерации: ${message}`, 'error');
            setGenerationDetails([message], 'error');
            document.getElementById('statusText').textContent = error.status === 429 ? 'AI-генерация ограничена rate limit' : 'Ошибка AI-генерации';
            showToast(`Ошибка AI-генерации: ${message}`, 'error');
        } finally {
            generationRequestInFlight = false;
            stopGenerationFunWait();
            setButtonLoading(loadingButtonId, false);
            setGenerationActionButtonsDisabled(false, loadingButtonId);
        }
    }

    async function regenerateWithLatexMode(mode) {
        const modeInput = document.getElementById('generationLatexMode');
        if (modeInput) modeInput.value = mode;
        const request = lastGenerationRequest ? cloneGenerationRequest(lastGenerationRequest) : collectGenerationRequest();
        request.fields = request.fields || {};
        request.fields.latex_mode = mode;
        await runGenerationRequest(request, mode === 'rich' ? 'regenerateRichBtn' : 'regenerateSafeBtn');
    }

    async function generateLatexFromAi() {
        lastGenerationResult = null;
        lastGenerationRawOutput = '';
        await runGenerationRequest(collectGenerationRequest(), 'generateLatexBtn');
    }

    async function retryLastGeneration() {
        if (!lastGenerationRequest) {
            setGenerationStatus('Нет сохранённого запроса для retry.', 'error');
            showToast('Сначала выполните AI-генерацию', 'error');
            return;
        }
        await runGenerationRequest(cloneGenerationRequest(lastGenerationRequest), 'retryGenerationBtn');
    }
