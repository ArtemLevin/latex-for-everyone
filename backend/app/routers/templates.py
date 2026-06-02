from fastapi import APIRouter, HTTPException
from app.schemas import TemplateResponse
from typing import Optional

router = APIRouter()


# Template data
TEMPLATES = [
    {
        "id": "article",
        "name": "Статья (article)",
        "description": "Стандартная научная статья с заголовком, аннотацией и секциями",
        "category": "Документ",
        "content": r"""\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}

\title{Заголовок статьи}
\author{Автор}
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
Аннотация статьи.
\end{abstract}

\section{Введение}
Текст введения.

\section{Основная часть}
Основной текст.

\section{Заключение}
Заключение.

\end{document}"""
    },
    {
        "id": "report",
        "name": "Отчёт (report)",
        "description": "Отчёт с главами и разделами, оглавлением",
        "category": "Документ",
        "content": r"""\documentclass[12pt,a4paper]{report}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}

\title{Название отчёта}
\author{Автор}
\date{\today}

\begin{document}

\maketitle
\tableofcontents
\newpage

\chapter{Введение}
Текст введения.

\chapter{Основная часть}
Основной текст.

\chapter{Заключение}
Заключение.

\end{document}"""
    },
    {
        "id": "beamer",
        "name": "Презентация (beamer)",
        "description": "Презентация для выступления слайдами",
        "category": "Презентация",
        "content": r"""\documentclass{beamer}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usetheme{Madrid}

\title{Название презентации}
\author{Автор}
\date{\today}

\begin{document}

\frame{\titlepage}

\begin{frame}{Введение}
    \begin{itemize}
        \item Первый пункт
        \item Второй пункт
        \item Третий пункт
    \end{itemize}
\end{frame}

\begin{frame}{Формулы}
    $$E = mc^2$$
\end{frame}

\end{document}"""
    },
    {
        "id": "book",
        "name": "Книга (book)",
        "description": "Книга с главами, частями и оглавлением",
        "category": "Документ",
        "content": r"""\documentclass[12pt,a4paper]{book}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}

\title{Название книги}
\author{Автор}
\date{\today}

\begin{document}

\frontmatter
\maketitle
\tableofcontents

\mainmatter

\part{Часть первая}

\chapter{Введение}
Текст главы.

\chapter{Основы}
Текст главы.

\part{Часть вторая}

\chapter{Продвинутые темы}
Текст главы.

\backmatter

\end{document}"""
    },
    {
        "id": "letter",
        "name": "Письмо (letter)",
        "description": "Официальное письмо",
        "category": "Документ",
        "content": r"""\documentclass[a4paper]{letter}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}

\address{Ваш адрес\\Город, Индекс}
\signature{Ваше Имя}

\begin{document}

\begin{letter}{Адресат\\Организация\\Город}

\opening{Уважаемый(ая),}

Текст письма.

\closing{С уважением,}

\end{letter}

\end{document}"""
    },
    {
        "id": "thesis",
        "name": "Диссертация (thesis)",
        "description": "Шаблон для дипломной работы / диссертации",
        "category": "Академический",
        "content": r"""\documentclass[12pt,a4paper]{report}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{geometry}
\geometry{left=3cm,right=1.5cm,top=2cm,bottom=2cm}

\begin{document}

\begin{titlepage}
\begin{center}
\vspace*{2cm}
{\Large \textbf{Название работы}}\\
\vspace{1cm}
{\large Дипломная работа}\\
\vspace{2cm}
Выполнил: Студент\\
\vspace{0.5cm}
Научный руководитель: Профессор\\
\vspace{2cm}
\date{\today}
\end{center}
\end{titlepage}

\tableofcontents
\newpage

\chapter{Введение}
\section{Актуальность темы}
Текст.

\section{Цель и задачи}
Текст.

\chapter{Обзор литературы}
Текст.

\chapter{Методология}
Текст.

\chapter{Результаты}
Текст.

\chapter{Заключение}
Текст.

\bibliographystyle{plain}
\bibliography{references}

\end{document}"""
    },
    {
        "id": "cv",
        "name": "Резюме (CV)",
        "description": "Академическое резюме / CV",
        "category": "Документ",
        "content": r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{hyperref}

\begin{document}

\begin{center}
{\LARGE \textbf{Иванов Иван Иванович}}\\
\vspace{0.3cm}
email@example.com | +7 (999) 123-45-67 | Москва
\end{center}

\hrule
\vspace{0.5cm}

\section*{Образование}
\textbf{МГУ им. М.В. Ломоносова} \hfill 2018--2022\\
Бакалавр, Факультет вычислительной математики и кибернетики

\section*{Опыт работы}
\textbf{Разработчик} — Компания \hfill 2022--н.в.\\
\begin{itemize}
    \item Разработка веб-приложений
    \item Работа с Python и FastAPI
\end{itemize}

\section*{Навыки}
\begin{itemize}
    \item Языки: Python, JavaScript, C++
    \item Фреймворки: FastAPI, React, Django
\end{itemize}

\end{document}"""
    },
    {
        "id": "minimal",
        "name": "Пустой документ",
        "description": "Минимальный пустой LaTeX документ",
        "category": "Базовый",
        "content": r"""\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{amsmath}
\usepackage{amssymb}

\begin{document}


\end{document}"""
    },
]


def get_template_content(template_id: str) -> Optional[dict]:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    return None


@router.get("/", response_model=list[TemplateResponse])
async def list_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
):
    templates = TEMPLATES

    if category:
        templates = [t for t in templates if t["category"].lower() == category.lower()]

    if search:
        search_lower = search.lower()
        templates = [
            t for t in templates
            if search_lower in t["name"].lower() or search_lower in t["description"].lower()
        ]

    return templates


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str):
    template = get_template_content(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template
