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
