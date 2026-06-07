import re


FIXED_LATEX_PREAMBLE = r"""\documentclass[a4paper,11pt]{article}

% UTF-8 and Russian support
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}

% Fonts and Math Packages
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}
\usepackage{mathtools}
\usepackage{amsthm}

% Layout and Structuring
\usepackage{geometry}
\geometry{
    a4paper,
    margin=2.3cm,
}

\usepackage{setspace}
\onehalfspacing

% Lists
\usepackage{enumitem}
\setlist{leftmargin=1.5em}

% Graphics and Tables
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{tabularx}
\usepackage{array}
\usepackage{colortbl}

\usepackage{tikz}
\usetikzlibrary{calc,intersections,through}

\usepackage{pgfplots}
\pgfplotsset{compat=1.18}

% Typography
\usepackage[expansion=false]{microtype}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage[most]{tcolorbox}

% Minimal colors
\definecolor{textgray}{HTML}{222222}
\definecolor{linegray}{HTML}{BBBBBB}

\color{textgray}

\hypersetup{
    colorlinks=true,
    linkcolor=textgray,
    urlcolor=textgray,
    citecolor=textgray,
}

% Section style
\titleformat{\section}[block]
  {\normalfont\Large\bfseries}
  {\thesection}
  {1em}
  {}

\titlespacing*{\section}{0pt}{2.5ex plus 1ex minus .2ex}{1.2ex}

\titleformat{\subsection}[block]
  {\normalfont\large\bfseries}
  {\thesubsection}
  {1em}
  {}

\titlespacing*{\subsection}{0pt}{2ex plus 1ex minus .2ex}{0.8ex}

% Minimal educational blocks
\newenvironment{infoblock}[1]
{
    \par\vspace{0.8em}
    \noindent
    \begin{minipage}{\textwidth}
    \hrule height 0.5pt
    \vspace{0.5em}
    \textbf{#1}\par
    \vspace{0.4em}
}
{
    \vspace{0.5em}
    \hrule height 0.5pt
    \end{minipage}
    \par\vspace{0.8em}
}

\newenvironment{taskblock}[1]
{
    \par\vspace{0.8em}
    \noindent
    \begin{minipage}{\textwidth}
    \hrule height 0.5pt
    \vspace{0.5em}
    \textbf{#1}\par
    \vspace{0.4em}
}
{
    \vspace{0.5em}
    \hrule height 0.5pt
    \end{minipage}
    \par\vspace{0.8em}
}

\newcommand{\answer}[1]{%
    \par\vspace{0.5em}
    \noindent\textbf{Ответ:} #1
    \par\vspace{0.5em}
}

\pagestyle{plain}"""

_DOCUMENT_BODY_RE = re.compile(r"\\begin\{document\}(?P<body>.*)\\end\{document\}", re.DOTALL)


def extract_document_body(content: str) -> str:
    """Return the body that should be placed inside the fixed document wrapper."""
    stripped = content.strip()
    match = _DOCUMENT_BODY_RE.search(stripped)
    if match:
        return match.group("body").strip()
    return stripped


def build_latex_document(body: str) -> str:
    """Wrap generated body-only LaTeX in the canonical Latexed preamble."""
    normalized_body = extract_document_body(body)
    return f"{FIXED_LATEX_PREAMBLE}\n\n\\begin{{document}}\n\n{normalized_body}\n\n\\end{{document}}"
