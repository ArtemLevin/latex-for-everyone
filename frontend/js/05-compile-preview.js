    // ==================== COMPILATION ====================
    async function compileLatex() {
        const btn = document.getElementById('compileBtn');
        btn.classList.add('compiling');
        btn.innerHTML = '<div class="spinner"></div><span>Компиляция...</span>';

        try {
            if (backendAvailable && currentProject) {
                await saveCurrentFile();
                const allFiles = collectFilesByName();
                const mainFile = Object.values(files).find(file => file.is_main) || files[currentFileId];
                const result = await apiRequest('/compile/', {
                    method: 'POST',
                    body: JSON.stringify({
                        project_id: currentProject.id,
                        main_file_content: mainFile?.content || editor.getValue(),
                        all_files: allFiles
                    })
                });

                if (result.status === 'success') {
                    document.getElementById('errorPanel').classList.remove('active');
                    document.getElementById('statusDot').className = 'status-dot';
                    document.getElementById('statusText').textContent = result.compile_time
                        ? `Скомпилировано за ${result.compile_time}`
                        : 'Скомпилировано';
                    if (result.pdf_url) {
                        showPdfPreview(result.pdf_url);
                    } else {
                        showHtmlPreviewFallback();
                    }
                } else {
                    showCompileError(result.error || 'Ошибка компиляции');
                }
            } else {
                compileLatexLocal();
            }
            document.getElementById('lastCompiled').textContent = 'Последняя компиляция: ' + new Date().toLocaleTimeString('ru');
        } catch (e) {
            showCompileError(e.message);
            if (!backendAvailable) {
                compileLatexLocal();
            }
        } finally {
            btn.classList.remove('compiling');
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>Компиляция</span>';
        }
    }

    function compileLatexLocal() {
        try {
            const content = editor.getValue();
            const rendered = renderLatex(content);
            document.getElementById('previewContent').innerHTML = rendered;
            document.getElementById('errorPanel').classList.remove('active');
            document.getElementById('statusDot').className = 'status-dot';
            document.getElementById('statusText').textContent = 'Локальный preview';
        } catch (e) {
            showCompileError(e.message);
        }
    }

    function renderLatex(content) {
        let html = content;

        // Remove comments
        html = html.replace(/%[^\n]*/g, '');

        // Extract preamble
        const preambleMatch = html.match(/\\documentclass\{[^}]+\}([\s\S]*?)\\begin\{document\}/);
        const preamble = preambleMatch ? preambleMatch[1] : '';

        // Extract title, author, date
        const titleMatch = html.match(/\\title\{([^}]*)\}/);
        const authorMatch = html.match(/\\author\{([^}]*)\}/);
        const dateMatch = html.match(/\\date\{([^}]*)\}/);

        // Process document body
        let body = html.replace(/\\documentclass\{[^}]+\}[\s\S]*?\\begin\{document\}/, '');
        body = body.replace(/\\end\{document\}[\s\S]*$/, '');

        let result = '';

        // Title/Author/Date
        if (titleMatch) {
            const title = processInlineLatex(titleMatch[1]);
            result += `<h1>${title}</h1>`;
            if (authorMatch) {
                result += `<p class="author">${processInlineLatex(authorMatch[1])}</p>`;
            }
            if (dateMatch) {
                const dateVal = dateMatch[1];
                result += `<p class="date">${dateVal === '\\today' ? new Date().toLocaleDateString('ru') : processInlineLatex(dateVal)}</p>`;
            }
            result += '<hr style="border: none; border-top: 1px solid #ccc; margin: 1.5em 0;">';
        }

        // Abstract
        body = body.replace(/\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/g, function(m, c) {
            return `<div class="abstract">${processInlineLatex(c.trim())}</div>`;
        });

        // Sections
        body = body.replace(/\\section\*?\{([^}]*)\}/g, '<h2>$1</h2>');
        body = body.replace(/\\subsection\*?\{([^}]*)\}/g, '<h3>$1</h3>');
        body = body.replace(/\\subsubsection\*?\{([^}]*)\}/g, '<h4>$1</h4>');

        // Bold, Italic, Underline
        body = body.replace(/\\textbf\{([^}]*)\}/g, '<strong>$1</strong>');
        body = body.replace(/\\textit\{([^}]*)\}/g, '<em>$1</em>');
        body = body.replace(/\\underline\{([^}]*)\}/g, '<u>$1</u>');
        body = body.replace(/\\texttt\{([^}]*)\}/g, '<code style="background:#f5f5f5;padding:2px 4px;border-radius:3px;font-family:monospace">$1</code>');
        body = body.replace(/\\emph\{([^}]*)\}/g, '<em>$1</em>');
        body = body.replace(/\\textsc\{([^}]*)\}/g, '<span style="font-variant:small-caps">$1</span>');

        // Footnote
        body = body.replace(/\\footnote\{([^}]*)\}/g, '<sup style="color:#6366f1;cursor:pointer" title="$1">†</sup>');

        // New paragraph
        body = body.replace(/\n\n/g, '</p><p>');
        body = body.replace(/\\\\/g, '<br>');

        // Line breaks within paragraphs
        body = body.replace(/\n/g, ' ');

        // Display equations $$...$$
        body = body.replace(/\$\$([\s\S]*?)\$\$/g, function(m, eq) {
            try {
                const rendered = katex.renderToString(eq.trim(), { displayMode: true, throwOnError: false });
                return `<div class="equation-block">${rendered}</div>`;
            } catch (e) {
                return `<div class="equation-block" style="color:red;font-family:monospace">${eq}</div>`;
            }
        });

        // Inline equations $...$
        body = body.replace(/\$([^$]+?)\$/g, function(m, eq) {
            try {
                return katex.renderToString(eq.trim(), { displayMode: false, throwOnError: false });
            } catch (e) {
                return `<span style="color:red;font-family:monospace">${eq}</span>`;
            }
        });

        // Itemize
        body = body.replace(/\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}/g, function(m, c) {
            const items = c.replace(/\\item\s*/g, '<li>').replace(/<\/li>/g, '</li>');
            return `<ul>${items}</ul>`;
        });

        // Enumerate
        body = body.replace(/\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}/g, function(m, c) {
            const items = c.replace(/\\item\s*/g, '<li>').replace(/<\/li>/g, '</li>');
            return `<ol>${items}</ol>`;
        });

        // Table
        body = body.replace(/\\begin\{table\}[\s\S]*?\\begin\{tabular\}\{[^}]*\}([\s\S]*?)\\end\{tabular\}[\s\S]*?\\end\{table\}/g, function(m, c) {
            let tableHtml = '<table>';
            const rows = c.trim().split('\\\\').map(r => r.trim()).filter(r => r);
            rows.forEach((row, i) => {
                const tag = i === 0 ? 'th' : 'td';
                const cells = row.replace(/\\hline/g, '').split('&').map(c => c.trim());
                tableHtml += '<tr>' + cells.map(c => `<${tag}>${processInlineLatex(c)}</${tag}>`).join('') + '</tr>';
            });
            tableHtml += '</table>';
            return tableHtml;
        });

        // Figure
        body = body.replace(/\\begin\{figure\}[\s\S]*?\\end\{figure\}/g, function(m) {
            const caption = m.match(/\\caption\{([^}]*)\}/);
            return `<figure style="text-align:center;margin:1.5em 0">
                <div style="background:#f0f0f0;padding:40px;border-radius:8px;color:#999">[Изображение]</div>
                ${caption ? `<figcaption style="margin-top:8px;font-size:0.9em;color:#666">${caption[1]}</figcaption>` : ''}
            </figure>`;
        });

        // Centering
        body = body.replace(/\\centering/g, '');

        // Clear page
        body = body.replace(/\\clearpage/g, '');
        body = body.replace(/\\newpage/g, '');

        // Part/Chapter (for book/report)
        body = body.replace(/\\part\*?\{([^}]*)\}/g, '<h1 style="text-align:center;margin:2em 0">$1</h1>');
        body = body.replace(/\\chapter\*?\{([^}]*)\}/g, '<h2 style="page-break-before:always">$1</h2>');

        // Table of contents placeholder
        body = body.replace(/\\tableofcontents/g, '<div style="text-align:center;color:#666;padding:1em">[Оглавление]</div>');

        // Maketitle placeholder (if not caught above)
        body = body.replace(/\\maketitle/g, '');

        // New line
        body = body.replace(/\\newline/g, '<br>');

        // Horizontal rule
        body = body.replace(/\\hrulefill/g, '<hr>');
        body = body.replace(/\\hrule/g, '<hr>');

        // Today
        body = body.replace(/\\today/g, new Date().toLocaleDateString('ru'));

        // Wrap in paragraphs
        result += `<p>${body}</p>`;

        return result;
    }

    function processInlineLatex(text) {
        // Process inline math in text
        text = text.replace(/\$([^$]+?)\$/g, function(m, eq) {
            try {
                return katex.renderToString(eq.trim(), { displayMode: false, throwOnError: false });
            } catch (e) {
                return eq;
            }
        });
        text = text.replace(/\\textbf\{([^}]*)\}/g, '<strong>$1</strong>');
        text = text.replace(/\\textit\{([^}]*)\}/g, '<em>$1</em>');
        text = text.replace(/\\emph\{([^}]*)\}/g, '<em>$1</em>');
        text = text.replace(/\\underline\{([^}]*)\}/g, '<u>$1</u>');
        text = text.replace(/\\texttt\{([^}]*)\}/g, '<code style="background:#f5f5f5;padding:2px 4px;border-radius:3px;font-family:monospace">$1</code>');
        text = text.replace(/\\cite\{([^}]*)\}/g, '[$1]');
        text = text.replace(/\\ref\{([^}]*)\}/g, '→$1');
        text = text.replace(/\\label\{([^}]*)\}/g, '');
        return text;
    }
