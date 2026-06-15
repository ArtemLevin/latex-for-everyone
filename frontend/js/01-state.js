    // ==================== STATE ====================
    let editor = null;
    let currentProject = null;
    let currentFileId = 'main';
    let autoCompile = false;
    let backendAvailable = false;
    let compileTimeout = null;
    let saveTimeout = null;
    let generationPresets = [];
    let lastGenerationPrompt = '';
    let lastGenerationRawOutput = '';
    let lastGenerationRequest = null;
    let lastGenerationResult = null;
    let generationRequestInFlight = false;
    let generationRateLimitedUntil = 0;
    let generationFunTimer = null;
    let generationFunStep = 0;
    let suppressEditorChange = false;
    let contextMenuFileId = null;
    let selectedCommandIndex = 0;
    let pdfPreviewDocument = null;
    let pdfPreviewUrl = '';
    let pdfPreviewPage = 1;
    let pdfPreviewScale = 1;
    let pdfPreviewFitMode = 'width';
    let pdfPreviewResizeTimer = null;
    let pdfPreviewRenderTask = null;
    window.pdfPreviewRenderTask = null;

    const LOCAL_PROJECT_KEY = 'latexed_project_id';
    const API_BASE_URL = getApiBaseUrl();
    const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, '');

    function getApiBaseUrl() {
        const configured = window.LATEXED_API_BASE_URL
            || document.querySelector('meta[name="latexed-api-base-url"]')?.content;
        if (configured) return configured.replace(/\/$/, '');

        const isHttp = window.location.protocol === 'http:' || window.location.protocol === 'https:';
        const isLocalFrontend = ['localhost', '127.0.0.1'].includes(window.location.hostname)
            && window.location.port
            && window.location.port !== '8000';
        const origin = isHttp && !isLocalFrontend ? window.location.origin : 'http://localhost:8000';
        return `${origin}/api`;
    }

    let files = {
        main: {
            name: 'main.tex',
            content: `\\documentclass[12pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}
\\usepackage{graphicx}
\\usepackage{hyperref}
\\usepackage{geometry}
\\geometry{margin=1in}

\\title{Введение в линейную алгебру}
\\author{Иванов И.И.}
\\date{\\today}

\\begin{document}

\\maketitle

\\begin{abstract}
В данной работе рассматриваются основные понятия линейной алгебры,
включая векторные пространства, линейные преобразования и собственные значения.
Представлены теоретические основы и практические примеры.
\\end{abstract}

\\section{Введение}

Линейная алгебра является одним из фундаментальных разделов математики.
Она изучает векторные пространства и линейные отображения между ними.

\\subsection{Определения}

\\textbf{Векторное пространство} --- это множество $V$, элементы которого
называются \\textit{векторами}, на котором определены две операции:

\\begin{enumerate}
\\item Сложение векторов: $\\vec{a} + \\vec{b} \\in V$
\\item Умножение на скаляр: $\\alpha \\cdot \\vec{a} \\in V$, где $\\alpha \\in \\mathbb{R}$
\\end{enumerate}

\\section{Матрицы и определители}

\\subsection{Операции с матрицами}

Рассмотрим матрицу $A$ размера $n \\times m$:

$$A = \\begin{pmatrix} a_{11} & a_{12} & \\cdots & a_{1m} \\\\ a_{21} & a_{22} & \\cdots & a_{2m} \\\\ \\vdots & \\vdots & \\ddots & \\vdots \\\\ a_{n1} & a_{n2} & \\cdots & a_{nm} \\end{pmatrix}$$

\\subsection{Определитель}

Определитель матрицы $2 \\times 2$ вычисляется по формуле:

$$\\det(A) = \\begin{vmatrix} a & b \\\\ c & d \\end{vmatrix} = ad - bc$$

Для матрицы $3 \\times 3$ используется правило Саррюса:

$$\\det(A) = a_{11}a_{22}a_{33} + a_{12}a_{23}a_{31} + a_{13}a_{21}a_{32} - a_{13}a_{22}a_{31} - a_{11}a_{23}a_{32} - a_{12}a_{21}a_{33}$$

\\section{Системы линейных уравнений}

Система $n$ линейных уравнений с $m$ неизвестными записывается в виде:

$$\\begin{cases} a_{11}x_1 + a_{12}x_2 + \\cdots + a_{1m}x_m = b_1 \\\\ a_{21}x_1 + a_{22}x_2 + \\cdots + a_{2m}x_m = b_2 \\\\ \\vdots \\\\ a_{n1}x_1 + a_{n2}x_2 + \\cdots + a_{nm}x_m = b_n \\end{cases}$$

В матричной форме: $A\\vec{x} = \\vec{b}$

\\section{Собственные значения и векторы}

\\textbf{Собственное значение} $\\lambda$ и \\textbf{собственный вектор} $\\vec{v}$
матрицы $A$ удовлетворяют уравнению:

$$A\\vec{v} = \\lambda\\vec{v}$$

Характеристическое уравнение:

$$\\det(A - \\lambda I) = 0$$

\\subsection{Пример}

Для матрицы $A = \\begin{pmatrix} 4 & 1 \\\\ 2 & 3 \\end{pmatrix}$:

$$\\det(A - \\lambda I) = \\begin{vmatrix} 4-\\lambda & 1 \\\\ 2 & 3-\\lambda \\end{vmatrix} = (4-\\lambda)(3-\\lambda) - 2 = \\lambda^2 - 7\\lambda + 10$$

Корни: $\\lambda_1 = 5$, $\\lambda_2 = 2$

\\section{Заключение}

Линейная алгебра находит широкое применение в различных областях:

\\begin{itemize}
\\item Физика --- квантовая механика, теория относительности
\\item Информатика --- машинное обучение, компьютерная графика
\\item Экономика --- моделирование, оптимизация
\\item Инженерия --- анализ цепей, теория управления
\\end{itemize}

\\section*{Формулы}

Некоторые важные формулы линейной алгебры:

$$e^{i\\pi} + 1 = 0$$

$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$

$$\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}$$

\\end{document}`
        },
        preamble: {
            name: 'preamble.tex',
            content: `%% Преамбула документа
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath, amssymb, amsthm}
\\usepackage{graphicx}
\\usepackage{hyperref}
\\usepackage{geometry}
\\geometry{margin=1in}

%% Теоремы
\\newtheorem{theorem}{Теорема}
\\newtheorem{lemma}{Лемма}
\\newtheorem{definition}{Определение}
\\newtheorem{example}{Пример}`
        },
        bibliography: {
            name: 'bibliography.bib',
            content: `@book{knuth1997,
author = {Knuth, Donald E.},
title = {The Art of Computer Programming},
year = {1997},
publisher = {Addison-Wesley},
volume = {1}
}

@article{einstein1905,
author = {Einstein, Albert},
title = {Zur Elektrodynamik bewegter Körper},
journal = {Annalen der Physik},
year = {1905},
volume = {322},
pages = {891--921}
}

@book{gilbert_strang,
author = {Strang, Gilbert},
title = {Introduction to Linear Algebra},
year = {2016},
publisher = {Wellesley-Cambridge Press},
edition = {5}
}`
        }
    };

    let templates = [
        {
            name: 'Статья (article)',
            desc: 'Стандартная научная статья с заголовком, аннотацией и секциями',
            content: `\\documentclass[12pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\title{Заголовок статьи}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\maketitle

\\begin{abstract}
Аннотация статьи.
\\end{abstract}

\\section{Введение}
Текст введения.

\\section{Основная часть}
Основной текст.

\\section{Заключение}
Заключение.

\\end{document}`
        },
        {
            name: 'Отчёт (report)',
            desc: 'Отчёт с главами и разделами',
            content: `\\documentclass[12pt,a4paper]{report}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\title{Название отчёта}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\maketitle
\\tableofcontents
\\newpage

\\chapter{Введение}
Текст введения.

\\chapter{Основная часть}
Основной текст.

\\chapter{Заключение}
Заключение.

\\end{document}`
        },
        {
            name: 'Презентация (beamer)',
            desc: 'Презентация для выступления',
            content: `\\documentclass{beamer}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usetheme{Madrid}

\\title{Название презентации}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\frame{\\titlepage}

\\begin{frame}{Введение}
\\begin{itemize}
    \\item Первый пункт
    \\item Второй пункт
    \\item Третий пункт
\\end{itemize}
\\end{frame}

\\begin{frame}{Формулы}
$$E = mc^2$$
\\end{frame}

\\end{document}`
        },
        {
            name: 'Книга (book)',
            desc: 'Книга с главами, частями и оглавлением',
            content: `\\documentclass[12pt,a4paper]{book}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\title{Название книги}
\\author{Автор}
\\date{\\today}

\\begin{document}

\\frontmatter
\\maketitle
\\tableofcontents

\\mainmatter

\\part{Часть первая}

\\chapter{Введение}
Текст главы.

\\chapter{Основы}
Текст главы.

\\part{Часть вторая}

\\chapter{Продвинутые темы}
Текст главы.

\\backmatter

\\end{document}`
        },
        {
            name: 'Письмо (letter)',
            desc: 'Официальное письмо',
            content: `\\documentclass[a4paper]{letter}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}

\\address{Ваш адрес\\\\Город, Индекс}
\\signature{Ваше Имя}

\\begin{document}

\\begin{letter}{Адресат\\\\Организация\\\\Город}

\\opening{Уважаемый(ая),}

Текст письма.

\\closing{С уважением,}

\\end{letter}

\\end{document}`
        },
        {
            name: 'Пустой документ',
            desc: 'Минимальный пустой LaTeX документ',
            content: `\\documentclass[12pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[russian]{babel}
\\usepackage{amsmath}
\\usepackage{amssymb}

\\begin{document}


\\end{document}`
        }
    ];
