// ==================== LESSON WORKFLOW ====================
let lessonPupils = [];
let lessonLessons = [];
let lessonDocuments = [];
let selectedLessonPupilId = '';
let selectedLessonId = '';
let selectedLessonRecordingId = '';
let selectedLessonTranscriptId = '';
let lastLessonJob = null;
let lessonMediaRecorder = null;
let lessonRecordedChunks = [];
let lessonRecordedBlob = null;
let lessonRecordedObjectUrl = '';
let lessonRecordingState = 'idle';
let lessonRecordingStartedAt = null;
let lessonRecordingElapsedMs = 0;
let lessonRecordingTimerId = null;
let lessonRecordingMimeType = '';
let lessonRecordingError = '';
let lessonRecordingByteSize = 0;
let lastLessonRecordingSummary = null;

const LESSON_RECORDING_MIME_CANDIDATES = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus'
];

const LESSON_RECORDING_STATE_LABELS = {
    idle: 'Запись не начата',
    requesting_permission: 'Запрашиваем доступ к микрофону…',
    recording: 'Идёт запись',
    stopped: 'Запись остановлена',
    ready_to_upload: 'Запись готова к загрузке',
    uploading: 'Загружаем аудио…',
    uploaded: 'Аудио загружено',
    failed: 'Ошибка записи',
    upload_failed: 'Ошибка загрузки'
};

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}


function formatLessonRecordingDuration(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
    const seconds = String(totalSeconds % 60).padStart(2, '0');
    return `${minutes}:${seconds}`;
}

function formatLessonRecordingBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 Б';
    const units = ['Б', 'КБ', 'МБ', 'ГБ'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }
    const precision = unitIndex === 0 ? 0 : 1;
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
}

function lessonRecordingExtensionForMime(mimeType) {
    const normalized = (mimeType || '').split(';', 1)[0].toLowerCase();
    if (normalized === 'audio/mp4') return 'm4a';
    if (normalized === 'audio/ogg') return 'ogg';
    if (normalized === 'audio/wav') return 'wav';
    return 'webm';
}

function chooseLessonRecordingMimeType() {
    if (!window.MediaRecorder) return '';
    if (typeof MediaRecorder.isTypeSupported !== 'function') return 'audio/webm';
    return LESSON_RECORDING_MIME_CANDIDATES.find(type => MediaRecorder.isTypeSupported(type)) || '';
}

function revokeLessonRecordedObjectUrl() {
    if (lessonRecordedObjectUrl) {
        URL.revokeObjectURL(lessonRecordedObjectUrl);
        lessonRecordedObjectUrl = '';
    }
}

function ensureLessonRecordedObjectUrl() {
    if (lessonRecordedBlob && !lessonRecordedObjectUrl) {
        lessonRecordedObjectUrl = URL.createObjectURL(lessonRecordedBlob);
    }
    return lessonRecordedObjectUrl;
}

function stopLessonRecordingTimer() {
    if (lessonRecordingTimerId) {
        clearInterval(lessonRecordingTimerId);
        lessonRecordingTimerId = null;
    }
}

function updateLessonRecordingMetrics() {
    if (lessonRecordingState === 'recording' && lessonRecordingStartedAt) {
        lessonRecordingElapsedMs = Date.now() - lessonRecordingStartedAt;
    }
    const timer = document.getElementById('lessonRecordingTimer');
    if (timer) timer.textContent = formatLessonRecordingDuration(lessonRecordingElapsedMs);
    const size = document.getElementById('lessonRecordingSize');
    if (size) size.textContent = formatLessonRecordingBytes(lessonRecordingByteSize);
}

function setLessonRecordingState(state, options = {}) {
    lessonRecordingState = state;
    if (Object.prototype.hasOwnProperty.call(options, 'error')) {
        lessonRecordingError = options.error || '';
    } else if (!['failed', 'upload_failed'].includes(state)) {
        lessonRecordingError = '';
    }
    if (Object.prototype.hasOwnProperty.call(options, 'bytes')) {
        lessonRecordingByteSize = options.bytes || 0;
    }
}

function resetLessonRecordingState({ keepUploaded = false } = {}) {
    stopLessonRecordingTimer();
    if (lessonMediaRecorder && lessonMediaRecorder.state !== 'inactive') {
        lessonMediaRecorder.stop();
    }
    lessonMediaRecorder = null;
    lessonRecordedChunks = [];
    lessonRecordedBlob = null;
    revokeLessonRecordedObjectUrl();
    lessonRecordingStartedAt = null;
    lessonRecordingElapsedMs = 0;
    lessonRecordingMimeType = '';
    lessonRecordingByteSize = 0;
    lessonRecordingError = '';
    if (!keepUploaded) lastLessonRecordingSummary = null;
    lessonRecordingState = keepUploaded ? 'uploaded' : 'idle';
}

function renderLessonRecordingCard() {
    const isRecording = lessonRecordingState === 'recording';
    const isBusy = ['requesting_permission', 'uploading'].includes(lessonRecordingState);
    const canStop = isRecording;
    const hasRecordedPreview = Boolean(lessonRecordedBlob);
    const previewUrl = ensureLessonRecordedObjectUrl();
    const supportMessage = (!navigator.mediaDevices || !window.MediaRecorder)
        ? '<div class="lesson-muted">MediaRecorder недоступен: используйте ручную загрузку аудиофайла.</div>'
        : '';
    const summary = lastLessonRecordingSummary
        ? `<div class="lesson-muted">Последняя запись: ${escapeHtml(lastLessonRecordingSummary.filename)} · ${escapeHtml(formatLessonRecordingBytes(lastLessonRecordingSummary.size_bytes || 0))}</div>`
        : '';
    const error = lessonRecordingError ? `<div class="lesson-recording-error">${escapeHtml(lessonRecordingError)}</div>` : '';
    const preview = hasRecordedPreview ? `
        <audio class="lesson-audio-preview" controls src="${escapeHtml(previewUrl)}"></audio>
        <div class="lesson-muted">Preview: ${escapeHtml(lessonRecordingMimeType || lessonRecordedBlob.type || 'audio')} · ${escapeHtml(formatLessonRecordingBytes(lessonRecordedBlob.size))}</div>
    ` : '';

    return `
        <div class="lesson-card lesson-recording-card" data-recording-state="${escapeHtml(lessonRecordingState)}">
            <strong>Audio recording</strong>
            <div class="lesson-recording-state">
                <span class="lesson-recording-dot"></span>
                <span>${escapeHtml(LESSON_RECORDING_STATE_LABELS[lessonRecordingState] || lessonRecordingState)}</span>
            </div>
            <div class="lesson-recording-metrics">
                <span>⏱ <span id="lessonRecordingTimer">${escapeHtml(formatLessonRecordingDuration(lessonRecordingElapsedMs))}</span></span>
                <span>💾 <span id="lessonRecordingSize">${escapeHtml(formatLessonRecordingBytes(lessonRecordingByteSize))}</span></span>
                <span>${escapeHtml(lessonRecordingMimeType || 'формат не выбран')}</span>
            </div>
            <label class="lesson-consent">
                <input id="lessonRecordingConsent" type="checkbox">
                <span>Подтверждаю право на запись и обработку аудио занятия.</span>
            </label>
            ${supportMessage}
            ${preview}
            ${summary}
            ${error}
            <div class="lesson-actions">
                <button class="lesson-action-btn" onclick="startLessonRecording()" ${isBusy || isRecording ? 'disabled' : ''}>Начать</button>
                <button class="lesson-action-btn" onclick="stopLessonRecording()" ${canStop ? '' : 'disabled'}>Стоп</button>
                <button class="lesson-action-btn" onclick="discardLessonRecording()" ${hasRecordedPreview || lessonRecordingState === 'failed' || lessonRecordingState === 'upload_failed' ? '' : 'disabled'}>Сброс</button>
            </div>
        </div>
    `;
}

async function lessonApiRequest(path, options = {}) {
    const requestOptions = { ...options };
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    requestOptions.headers = headers;
    const response = await fetch(`${API_BASE_URL}${path}`, requestOptions);
    if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
            const data = await response.json();
            message = data.detail || message;
        } catch (error) {
            message = response.statusText || message;
        }
        throw new Error(message);
    }
    if (response.status === 204) return null;
    return response.json();
}

function renderLessonSidebar(message = '') {
    const tree = document.getElementById('fileTree');
    const footer = document.querySelector('.sidebar-footer');
    const title = document.querySelector('.sidebar-title');
    if (!tree) return;
    if (footer) footer.style.display = 'none';
    if (title) title.textContent = 'Уроки';

    const pupilOptions = lessonPupils.map(pupil => `
        <option value="${escapeHtml(pupil.id)}" ${pupil.id === selectedLessonPupilId ? 'selected' : ''}>${escapeHtml(pupil.display_name)}</option>
    `).join('');
    const lessonOptions = lessonLessons.map(lesson => `
        <option value="${escapeHtml(lesson.id)}" ${lesson.id === selectedLessonId ? 'selected' : ''}>${escapeHtml(lesson.topic)} · ${escapeHtml((lesson.lesson_date || '').slice(0, 10))}</option>
    `).join('');
    const docsHtml = lessonDocuments.length
        ? lessonDocuments.map(doc => `
            <a class="lesson-doc-link" href="${escapeHtml(resolveApiUrl(doc.download_url))}" target="_blank" rel="noopener">
                ${escapeHtml(doc.title || doc.document_type)}
            </a>
        `).join('')
        : '<div class="lesson-muted">Документы ещё не созданы</div>';

    tree.innerHTML = `
        <div class="lesson-panel">
            <div class="lesson-status ${backendAvailable ? 'online' : 'offline'}">
                Backend: ${backendAvailable ? 'подключён' : 'недоступен'}
            </div>
            ${message ? `<div class="lesson-message">${escapeHtml(message)}</div>` : ''}
            <label class="lesson-label" for="lessonPupilName">Новый ученик</label>
            <div class="lesson-inline-form">
                <input class="lesson-input" id="lessonPupilName" placeholder="Имя ученика">
                <button class="lesson-small-btn" onclick="createLessonPupil()">+</button>
            </div>
            <label class="lesson-label" for="lessonPupilSelect">Ученик</label>
            <select class="lesson-input" id="lessonPupilSelect" onchange="selectLessonPupil(this.value)">
                <option value="">Выберите ученика</option>
                ${pupilOptions}
            </select>
            <label class="lesson-label" for="lessonTopicInput">Тема занятия</label>
            <div class="lesson-inline-form">
                <input class="lesson-input" id="lessonTopicInput" placeholder="Например: квадратные уравнения">
                <button class="lesson-small-btn" onclick="createLessonForSelectedPupil()">Создать</button>
            </div>
            <label class="lesson-label" for="lessonSelect">Занятие</label>
            <select class="lesson-input" id="lessonSelect" onchange="selectLesson(this.value)">
                <option value="">Выберите занятие</option>
                ${lessonOptions}
            </select>
            <div class="lesson-actions">
                <button class="lesson-action-btn" onclick="refreshLessonsWorkflow()">Обновить</button>
            </div>
            ${renderLessonRecordingCard()}
            <label class="lesson-label" for="lessonAudioInput">Аудио файл</label>
            <input class="lesson-input" id="lessonAudioInput" type="file" accept="audio/webm,audio/wav,audio/mpeg,audio/mp4,audio/ogg,audio/x-m4a,.webm,.wav,.mp3,.m4a,.ogg">
            <div class="lesson-actions">
                <button class="lesson-action-btn" onclick="uploadLessonAudio()" ${lessonRecordingState === 'uploading' || lessonRecordingState === 'recording' ? 'disabled' : ''}>Загрузить</button>
                <button class="lesson-action-btn" onclick="startLessonProcessingJob()">Pipeline job</button>
            </div>
            <div class="lesson-actions">
                <button class="lesson-action-btn" onclick="transcribeLesson()">Транскрибировать</button>
                <button class="lesson-action-btn" onclick="generateLessonDocuments()">Документы</button>
            </div>
            <div class="lesson-card">
                <strong>Job</strong>
                <div id="lessonJobStatus">${lastLessonJob ? `${escapeHtml(lastLessonJob.status)} · ${escapeHtml(lastLessonJob.stage)}` : 'нет job'}</div>
            </div>
            <div class="lesson-card">
                <strong>Transcript</strong>
                <div class="lesson-transcript" id="lessonTranscriptPreview">${selectedLessonTranscriptId ? 'Transcript создан' : 'Transcript ещё не создан'}</div>
            </div>
            <div class="lesson-card">
                <strong>Documents</strong>
                <div class="lesson-docs" id="lessonDocumentsList">${docsHtml}</div>
            </div>
        </div>
    `;
}

async function refreshLessonsWorkflow() {
    if (!backendAvailable) {
        renderLessonSidebar('Backend недоступен: уроки доступны только после подключения API.');
        return;
    }
    try {
        lessonPupils = await lessonApiRequest('/pupils/');
        if (!selectedLessonPupilId && lessonPupils.length) selectedLessonPupilId = lessonPupils[0].id;
        await loadLessonsForSelectedPupil();
        renderLessonSidebar();
    } catch (error) {
        renderLessonSidebar(`Не удалось загрузить уроки: ${error.message}`);
        showToast(`Ошибка уроков: ${error.message}`, 'error');
    }
}

async function loadLessonsForSelectedPupil() {
    if (!selectedLessonPupilId) {
        lessonLessons = [];
        selectedLessonId = '';
        return;
    }
    lessonLessons = await lessonApiRequest(`/lessons/?pupil_id=${encodeURIComponent(selectedLessonPupilId)}`);
    if (!lessonLessons.some(lesson => lesson.id === selectedLessonId)) {
        selectedLessonId = lessonLessons[0]?.id || '';
    }
    if (selectedLessonId) await loadLessonDocuments();
}

async function createLessonPupil() {
    const input = document.getElementById('lessonPupilName');
    const displayName = input?.value.trim();
    if (!displayName) return showToast('Введите имя ученика', 'error');
    try {
        const pupil = await lessonApiRequest('/pupils/', {
            method: 'POST',
            body: JSON.stringify({ display_name: displayName })
        });
        selectedLessonPupilId = pupil.id;
        await refreshLessonsWorkflow();
        showToast('Ученик создан', 'success');
    } catch (error) {
        showToast(`Ошибка создания ученика: ${error.message}`, 'error');
    }
}

async function selectLessonPupil(pupilId) {
    selectedLessonPupilId = pupilId;
    selectedLessonId = '';
    selectedLessonRecordingId = '';
    selectedLessonTranscriptId = '';
    resetLessonRecordingState();
    await loadLessonsForSelectedPupil();
    renderLessonSidebar();
}

async function createLessonForSelectedPupil() {
    if (!selectedLessonPupilId) return showToast('Сначала выберите ученика', 'error');
    const input = document.getElementById('lessonTopicInput');
    const topic = input?.value.trim();
    if (!topic) return showToast('Введите тему занятия', 'error');
    try {
        const lesson = await lessonApiRequest('/lessons/', {
            method: 'POST',
            body: JSON.stringify({ pupil_id: selectedLessonPupilId, topic })
        });
        selectedLessonId = lesson.id;
        await loadLessonsForSelectedPupil();
        renderLessonSidebar();
        showToast('Занятие создано', 'success');
    } catch (error) {
        showToast(`Ошибка создания занятия: ${error.message}`, 'error');
    }
}

async function selectLesson(lessonId) {
    selectedLessonId = lessonId;
    selectedLessonRecordingId = '';
    selectedLessonTranscriptId = '';
    lastLessonJob = null;
    resetLessonRecordingState();
    await loadLessonDocuments();
    renderLessonSidebar();
}

async function uploadLessonAudio() {
    if (!selectedLessonId) return showToast('Сначала выберите занятие', 'error');
    if (lessonRecordingState === 'recording') return showToast('Сначала остановите запись', 'error');
    const input = document.getElementById('lessonAudioInput');
    const extension = lessonRecordingExtensionForMime(lessonRecordingMimeType || lessonRecordedBlob?.type);
    const file = lessonRecordedBlob
        ? new File([lessonRecordedBlob], `lesson-${Date.now()}.${extension}`, { type: lessonRecordedBlob.type || lessonRecordingMimeType || 'audio/webm' })
        : input?.files?.[0];
    if (!file) return showToast('Выберите или запишите аудио', 'error');
    const formData = new FormData();
    formData.append('file', file, file.name);
    setLessonRecordingState('uploading', { bytes: file.size });
    renderLessonSidebar('Загружаем аудио…');
    try {
        const recording = await lessonApiRequest(`/lessons/${selectedLessonId}/recordings`, {
            method: 'POST',
            body: formData
        });
        selectedLessonRecordingId = recording.id;
        lastLessonRecordingSummary = recording;
        lessonRecordedBlob = null;
        revokeLessonRecordedObjectUrl();
        lessonRecordedChunks = [];
        lessonRecordingElapsedMs = 0;
        lessonRecordingMimeType = recording.content_type || file.type || '';
        setLessonRecordingState('uploaded', { bytes: recording.size_bytes || file.size });
        showToast('Аудио загружено', 'success');
        renderLessonSidebar(`Аудио загружено: ${recording.filename}`);
    } catch (error) {
        setLessonRecordingState('upload_failed', { error: error.message, bytes: file.size });
        renderLessonSidebar(`Ошибка загрузки аудио: ${error.message}`);
        showToast(`Ошибка загрузки аудио: ${error.message}`, 'error');
    }
}

async function startLessonRecording() {
    if (!selectedLessonId) return showToast('Сначала выберите занятие', 'error');
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        setLessonRecordingState('failed', { error: 'MediaRecorder недоступен: загрузите аудиофайл вручную' });
        renderLessonSidebar();
        return showToast('MediaRecorder недоступен: загрузите аудиофайл вручную', 'error');
    }
    const consent = document.getElementById('lessonRecordingConsent');
    if (!consent?.checked) {
        setLessonRecordingState('failed', { error: 'Подтвердите право на запись и обработку аудио занятия' });
        renderLessonSidebar();
        return showToast('Подтвердите право на запись аудио', 'error');
    }
    const mimeType = chooseLessonRecordingMimeType();
    if (!mimeType) {
        setLessonRecordingState('failed', { error: 'Браузер не поддерживает разрешённые форматы записи. Загрузите аудиофайл вручную.' });
        renderLessonSidebar();
        return showToast('Браузер не поддерживает запись в разрешённом audio-формате', 'error');
    }
    try {
        resetLessonRecordingState();
        lessonRecordingMimeType = mimeType;
        setLessonRecordingState('requesting_permission');
        renderLessonSidebar('Запрашиваем доступ к микрофону…');
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        lessonRecordedChunks = [];
        lessonRecordingByteSize = 0;
        const options = mimeType ? { mimeType } : undefined;
        lessonMediaRecorder = new MediaRecorder(stream, options);
        lessonMediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                lessonRecordedChunks.push(event.data);
                lessonRecordingByteSize += event.data.size;
                updateLessonRecordingMetrics();
            }
        };
        lessonMediaRecorder.onerror = event => {
            const message = event.error?.message || 'Ошибка MediaRecorder';
            setLessonRecordingState('failed', { error: message });
            stream.getTracks().forEach(track => track.stop());
            stopLessonRecordingTimer();
            renderLessonSidebar(message);
        };
        lessonMediaRecorder.onstop = () => {
            stream.getTracks().forEach(track => track.stop());
            stopLessonRecordingTimer();
            const blobType = lessonRecordingMimeType || lessonMediaRecorder.mimeType || 'audio/webm';
            lessonRecordedBlob = new Blob(lessonRecordedChunks, { type: blobType });
            lessonRecordingByteSize = lessonRecordedBlob.size;
            if (!lessonRecordedBlob.size) {
                setLessonRecordingState('failed', { error: 'Запись не содержит аудиоданных' });
                renderLessonSidebar('Запись не содержит аудиоданных. Попробуйте ещё раз.');
                return;
            }
            setLessonRecordingState('ready_to_upload', { bytes: lessonRecordedBlob.size });
            renderLessonSidebar('Запись готова: прослушайте preview и нажмите «Загрузить».');
        };
        lessonMediaRecorder.start(1000);
        lessonRecordingStartedAt = Date.now();
        setLessonRecordingState('recording');
        lessonRecordingTimerId = setInterval(updateLessonRecordingMetrics, 1000);
        renderLessonSidebar('Идёт запись audio…');
    } catch (error) {
        stopLessonRecordingTimer();
        setLessonRecordingState('failed', { error: error.message });
        renderLessonSidebar(`Не удалось начать запись: ${error.message}`);
        showToast(`Не удалось начать запись: ${error.message}`, 'error');
    }
}

function stopLessonRecording() {
    if (lessonMediaRecorder && lessonMediaRecorder.state !== 'inactive') {
        lessonRecordingElapsedMs = lessonRecordingStartedAt ? Date.now() - lessonRecordingStartedAt : lessonRecordingElapsedMs;
        setLessonRecordingState('stopped');
        lessonMediaRecorder.stop();
        showToast('Запись остановлена', 'info');
        renderLessonSidebar('Останавливаем запись…');
    }
}

function discardLessonRecording() {
    resetLessonRecordingState({ keepUploaded: Boolean(selectedLessonRecordingId && lastLessonRecordingSummary) });
    renderLessonSidebar('Локальная запись сброшена.');
}

async function transcribeLesson() {
    if (!selectedLessonId) return showToast('Сначала выберите занятие', 'error');
    try {
        const transcript = await lessonApiRequest(`/lessons/${selectedLessonId}/transcribe`, {
            method: 'POST',
            body: JSON.stringify({ recording_id: selectedLessonRecordingId || null })
        });
        selectedLessonTranscriptId = transcript.id;
        renderLessonSidebar(transcript.status === 'failed' ? transcript.error_message : 'Transcript создан.');
        showToast(transcript.status === 'failed' ? 'Транскрибация завершилась ошибкой' : 'Transcript создан', transcript.status === 'failed' ? 'error' : 'success');
    } catch (error) {
        showToast(`Ошибка транскрибации: ${error.message}`, 'error');
    }
}

async function generateLessonDocuments() {
    if (!selectedLessonId) return showToast('Сначала выберите занятие', 'error');
    try {
        const documents = await lessonApiRequest(`/lessons/${selectedLessonId}/documents/generate`, {
            method: 'POST',
            body: JSON.stringify({ transcript_id: selectedLessonTranscriptId || null })
        });
        lessonDocuments = documents;
        renderLessonSidebar('Документы созданы.');
        showToast('Документы урока готовы', 'success');
    } catch (error) {
        showToast(`Ошибка генерации документов: ${error.message}`, 'error');
    }
}

async function startLessonProcessingJob() {
    if (!selectedLessonId) return showToast('Сначала выберите занятие', 'error');
    try {
        const job = await lessonApiRequest(`/lessons/${selectedLessonId}/processing-jobs`, {
            method: 'POST',
            body: JSON.stringify({
                job_type: 'full_pipeline',
                recording_id: selectedLessonRecordingId || null,
                transcript_id: selectedLessonTranscriptId || null
            })
        });
        lastLessonJob = job;
        if (job.transcript_id) selectedLessonTranscriptId = job.transcript_id;
        await loadLessonDocuments();
        renderLessonSidebar(job.status === 'failed' ? job.error_message : `Job ${job.status}`);
        showToast(`Lesson job: ${job.status}`, job.status === 'failed' ? 'error' : 'success');
    } catch (error) {
        showToast(`Ошибка lesson job: ${error.message}`, 'error');
    }
}

async function loadLessonDocuments() {
    if (!backendAvailable || !selectedLessonId) {
        lessonDocuments = [];
        return;
    }
    try {
        lessonDocuments = await lessonApiRequest(`/lessons/${selectedLessonId}/documents`);
    } catch (error) {
        lessonDocuments = [];
    }
}

window.renderLessonSidebar = renderLessonSidebar;
window.refreshLessonsWorkflow = refreshLessonsWorkflow;
window.createLessonPupil = createLessonPupil;
window.selectLessonPupil = selectLessonPupil;
window.createLessonForSelectedPupil = createLessonForSelectedPupil;
window.selectLesson = selectLesson;
window.uploadLessonAudio = uploadLessonAudio;
window.startLessonRecording = startLessonRecording;
window.stopLessonRecording = stopLessonRecording;
window.discardLessonRecording = discardLessonRecording;
window.transcribeLesson = transcribeLesson;
window.generateLessonDocuments = generateLessonDocuments;
window.startLessonProcessingJob = startLessonProcessingJob;
