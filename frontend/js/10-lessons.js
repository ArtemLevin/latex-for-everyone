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

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
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
                <button class="lesson-action-btn" onclick="startLessonRecording()">Запись</button>
                <button class="lesson-action-btn" onclick="stopLessonRecording()">Стоп</button>
            </div>
            <label class="lesson-label" for="lessonAudioInput">Аудио</label>
            <input class="lesson-input" id="lessonAudioInput" type="file" accept="audio/*">
            <div class="lesson-actions">
                <button class="lesson-action-btn" onclick="uploadLessonAudio()">Загрузить</button>
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
    await loadLessonDocuments();
    renderLessonSidebar();
}

async function uploadLessonAudio() {
    if (!selectedLessonId) return showToast('Сначала выберите занятие', 'error');
    const input = document.getElementById('lessonAudioInput');
    const file = lessonRecordedBlob
        ? new File([lessonRecordedBlob], `lesson-${Date.now()}.webm`, { type: lessonRecordedBlob.type || 'audio/webm' })
        : input?.files?.[0];
    if (!file) return showToast('Выберите или запишите аудио', 'error');
    const formData = new FormData();
    formData.append('file', file, file.name);
    try {
        const recording = await lessonApiRequest(`/lessons/${selectedLessonId}/recordings`, {
            method: 'POST',
            body: formData
        });
        selectedLessonRecordingId = recording.id;
        lessonRecordedBlob = null;
        showToast('Аудио загружено', 'success');
        renderLessonSidebar(`Аудио загружено: ${recording.filename}`);
    } catch (error) {
        showToast(`Ошибка загрузки аудио: ${error.message}`, 'error');
    }
}

async function startLessonRecording() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        return showToast('MediaRecorder недоступен: загрузите аудиофайл вручную', 'error');
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        lessonRecordedChunks = [];
        lessonMediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        lessonMediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) lessonRecordedChunks.push(event.data);
        };
        lessonMediaRecorder.onstop = () => {
            lessonRecordedBlob = new Blob(lessonRecordedChunks, { type: 'audio/webm' });
            stream.getTracks().forEach(track => track.stop());
            renderLessonSidebar('Запись готова: нажмите «Загрузить».');
        };
        lessonMediaRecorder.start();
        renderLessonSidebar('Идёт запись audio…');
    } catch (error) {
        showToast(`Не удалось начать запись: ${error.message}`, 'error');
    }
}

function stopLessonRecording() {
    if (lessonMediaRecorder && lessonMediaRecorder.state !== 'inactive') {
        lessonMediaRecorder.stop();
        showToast('Запись остановлена', 'info');
    }
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
window.transcribeLesson = transcribeLesson;
window.generateLessonDocuments = generateLessonDocuments;
window.startLessonProcessingJob = startLessonProcessingJob;
