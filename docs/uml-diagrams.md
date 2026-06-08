# UML-диаграммы работы Latexed

Этот документ описывает работу репозитория Latexed через UML-диаграммы в формате Mermaid. Диаграммы построены по текущей структуре проекта: FastAPI backend, браузерный SPA frontend, SQLAlchemy-модели, сервисы компиляции/export/AI и Alembic-миграции.

## 1. Контекст системы

Latexed — онлайн-редактор LaTeX. Пользователь работает в браузере с CodeMirror/KaTeX/PDF.js, frontend вызывает REST API backend, backend хранит проекты и файлы в базе данных, запускает `pdflatex` для серверной компиляции/export и обращается к AI-провайдеру для генерации LaTeX.

```mermaid
flowchart LR
    User["Пользователь"] --> Browser["Frontend SPA\nfrontend/main.html + frontend/js"]

    Browser -->|"REST /api/*"| Backend["FastAPI backend\nbackend/app/main.py"]
    Browser -->|"offline fallback"| LocalPreview["Локальный preview/export\nKaTeX + html2pdf.js"]

    Backend --> Routers["API routers\nprojects/files/compile/export/templates/generation"]
    Routers --> Services["Services\ncompiler, PDF, AI, validation, persistence"]
    Services --> DB[("SQLite/PostgreSQL\nSQLAlchemy models")]
    Services --> Latex["pdflatex\nсерверная компиляция"]
    Services --> AI["AI provider\nOllama/OpenAI-compatible"]

    Backend --> Artifacts["Runtime artifacts\nPDF/TEX/HTML in temp dirs"]
```

## 2. Компонентная диаграмма backend и frontend

Основная архитектурная граница backend: `Router → Service → Database/session/model`. Часть CRUD-роутеров всё ещё работает с SQLAlchemy напрямую как существующий legacy-паттерн, но новая нетривиальная логика должна уходить в сервисы.

```mermaid
flowchart TB
    subgraph Frontend["frontend/"]
        MainHtml["main.html\nDOM shell + CDN libs"]
        State["01-state.js\nглобальное состояние"]
        Api["02-api.js\nAPI base, requests, PDF helpers"]
        Init["03-init.js\nstartup/editor bootstrap"]
        FilesUI["04-files.js\nfile tree"]
        CompileUI["05-compile-preview.js\ncompile + preview"]
        ToolbarUI["06-toolbar-view.js\ntoolbar/view"]
        AiUI["07-generation.js\nAI generation UI"]
        ExportUI["08-templates-export.js\ntemplates/export"]
        SettingsUI["09-ui-settings.js\nsettings/toasts/commands"]
    end

    MainHtml --> State --> Api --> Init --> FilesUI --> CompileUI --> ToolbarUI --> AiUI --> ExportUI --> SettingsUI

    subgraph Backend["backend/app/"]
        App["main.py\nFastAPI app, middleware, routes"]
        DBSession["database.py\nengine/session/get_db"]
        Schemas["schemas.py\nPydantic API contracts"]
        Models["models.py\nSQLAlchemy entities"]

        subgraph Routers["routers/"]
            ProjectsRouter["projects.py"]
            FilesRouter["files.py"]
            CompileRouter["compile.py"]
            ExportRouter["export.py"]
            TemplatesRouter["templates.py"]
            GenerationRouter["generation.py"]
        end

        subgraph Services["services/"]
            ProjectService["project_service.py"]
            FileService["file_service.py"]
            Compiler["latex_compiler.py"]
            Sanitizer["latex_sanitizer.py\nlatex_file_policy.py\npayload_limits.py"]
            PdfService["pdf_generator.py"]
            AiService["ai_generation.py"]
            PromptService["prompt_builder.py"]
            Validator["latex_validator.py"]
            HistoryService["generation_history_service.py"]
        end
    end

    Api -->|"fetch /api/*"| App
    App --> Routers
    Routers --> Schemas
    ProjectsRouter --> ProjectService
    FilesRouter --> FileService
    CompileRouter --> Compiler
    CompileRouter --> Sanitizer
    ExportRouter --> PdfService
    GenerationRouter --> PromptService
    GenerationRouter --> AiService
    GenerationRouter --> Validator
    GenerationRouter --> HistoryService

    ProjectService --> DBSession
    FileService --> DBSession
    HistoryService --> DBSession
    Routers --> DBSession
    DBSession --> Models
```

## 3. Диаграмма классов данных и API-контрактов

SQLAlchemy-модели представляют persisted-сущности, а Pydantic-схемы задают контракты API и границы сервисов.

```mermaid
classDiagram
    class Project {
        +str id
        +str name
        +str owner_id
        +bool is_public
        +dict settings
        +datetime created_at
        +datetime updated_at
    }

    class File {
        +str id
        +str project_id
        +str name
        +str content
        +bool is_main
        +datetime created_at
        +datetime updated_at
    }

    class CompileHistory {
        +str id
        +str project_id
        +str status
        +str output
        +str error
        +str compile_time
        +datetime created_at
    }

    class ProjectSnapshot {
        +str id
        +str project_id
        +str name
        +dict data
        +datetime created_at
    }

    class GenerationHistory {
        +str id
        +str project_id
        +str provider
        +str model
        +str prompt_hash
        +str latex_hash
        +str status
        +int input_tokens
        +int output_tokens
        +int total_tokens
        +datetime created_at
    }

    Project "1" --> "many" File : files
    Project "1" --> "many" CompileHistory : compile_history
    Project "1" --> "many" ProjectSnapshot : snapshots
    Project "1" --> "many" GenerationHistory : generation_history

    class ProjectCreate {
        +str name
        +bool is_public
        +str template
    }
    class ProjectResponse {
        +str id
        +str name
        +bool is_public
        +dict settings
    }
    class FileCreate {
        +str name
        +str content
        +bool is_main
    }
    class CompileRequest {
        +str project_id
        +str main_file_name
        +str main_file_content
        +dict all_files
    }
    class CompileResponse {
        +str status
        +str output
        +str error
        +str compile_time
        +str pdf_url
        +str history_id
    }
    class ExportRequest {
        +str project_id
        +str format
        +dict content
    }
    class GenerationRequest {
        +str provider
        +str model
        +GenerationFields fields
        +str materials
        +str project_id
    }
    class GenerationResultResponse {
        +str status
        +str prompt
        +str latex_code
        +Validation validation
        +CompileCheck compile_check
        +TokenUsage token_usage
    }
```

## 4. Последовательность запуска приложения в браузере

Frontend загружается как набор ordered browser scripts. При старте он определяет адрес API, проверяет `/api/health`, загружает/создаёт проект, получает файлы и шаблоны, затем инициализирует редактор и preview. Если backend недоступен, сохраняется локальная работоспособность preview/export fallback.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant H as frontend/main.html
    participant JS as frontend/js modules
    participant API as FastAPI /api
    participant DB as Database
    participant Local as Local preview fallback

    U->>H: Открывает main.html
    H->>JS: Загружает 01-state → ... → 09-ui-settings
    JS->>API: GET /api/health
    alt backend доступен
        API-->>JS: status=healthy
        JS->>API: GET /api/projects/{saved_id} или POST /api/projects/
        API->>DB: Читает или создаёт Project
        DB-->>API: Project
        API-->>JS: ProjectResponse
        JS->>API: GET /api/files/project/{project_id}
        API->>DB: Загружает File[]
        API-->>JS: FileResponse[]
        JS->>API: GET /api/templates/
        API-->>JS: TemplateResponse[]
    else backend недоступен
        API--xJS: network/error
        JS->>Local: Создаёт локальный проект и main.tex
    end
    JS->>JS: Инициализирует CodeMirror, file tree, toolbar
    JS->>Local: Рендерит локальный KaTeX preview
```

## 5. Последовательность CRUD для проектов и файлов

Файловые операции проходят через frontend tree/editor, API-роутеры и сервисы/модели. Для проектов доступны создание, чтение, обновление, удаление, snapshots, restore и duplicate.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant UI as File tree / Editor
    participant API as /api/projects + /api/files
    participant Service as project_service/file_service
    participant DB as SQLAlchemy session

    U->>UI: Создаёт проект или файл
    UI->>API: POST /api/projects/ или POST /api/files/project/{project_id}
    API->>Service: create_project/create_file
    Service->>DB: INSERT Project/File
    DB-->>Service: persisted entity
    Service-->>API: entity
    API-->>UI: ProjectResponse/FileResponse

    U->>UI: Редактирует LaTeX
    UI->>API: PUT /api/files/{file_id}
    API->>Service: update_file
    Service->>DB: UPDATE File.content/name/is_main
    API-->>UI: FileResponse

    U->>UI: Создаёт snapshot или restore
    UI->>API: POST /api/projects/{id}/snapshot или /restore
    API->>Service: snapshot_project/restore_project_snapshot
    Service->>DB: Читает/пишет ProjectSnapshot и File[]
    API-->>UI: MessageResponse/SnapshotResponse
```

## 6. Последовательность серверной компиляции LaTeX

Серверная компиляция получает файлы проекта или raw-content, валидирует имена/расширения и лимиты payload, создаёт запись истории, запускает `pdflatex` в изолированной временной директории и возвращает ссылку на PDF или ошибку.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant UI as Compile UI
    participant R as compile router
    participant DB as Database
    participant Policy as file policy + payload limits
    participant C as LatexCompiler
    participant P as pdflatex
    participant FS as compile output dir

    U->>UI: Нажимает Compile
    UI->>R: POST /api/compile/ {project_id, main_file, all_files}
    R->>DB: SELECT Project + File[]
    DB-->>R: project files
    R->>Policy: validate filenames/extensions/size/count
    alt policy violation
        Policy-->>R: error
        R-->>UI: 400/413
    else payload ok
        R->>DB: INSERT CompileHistory(status=pending)
        R->>C: compile(main_content, files, main_filename)
        C->>FS: Создаёт временную рабочую директорию и sanitizes files
        C->>P: Запускает pdflatex с timeout
        P-->>C: PDF/log/error output
        C->>FS: Копирует PDF в output directory
        C-->>R: LatexCompileResult
        R->>DB: UPDATE CompileHistory(status/output/error/time)
        R-->>UI: CompileResponse(pdf_url, history_id)
    end
```

## 7. Последовательность export PDF/HTML/TEX

Export-роутер поддерживает форматы PDF, HTML и TEX. PDF использует сервис генерации PDF и `pdflatex`; HTML/TEX формируются как скачиваемые артефакты. Frontend сохраняет локальные fallback-варианты, если backend недоступен.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant UI as Export UI
    participant R as export router
    participant DB as Database
    participant PDF as PDFGenerator
    participant Latex as pdflatex
    participant FS as export output dir
    participant Local as html2pdf.js/local download

    U->>UI: Выбирает Export PDF/HTML/TEX
    UI->>R: POST /api/export/{format}
    alt backend доступен, PDF
        R->>DB: Загружает project/files или request.content
        R->>PDF: generate_pdf(project/content)
        PDF->>Latex: pdflatex
        Latex-->>PDF: PDF/log
        PDF->>FS: Сохраняет PDF
        PDF-->>R: PDFGenerationResult
        R-->>UI: ExportResponse(url, filename, size)
        UI->>R: GET /api/export/download/{filename}
    else backend доступен, HTML/TEX
        R->>DB: Загружает project/files или request.content
        R->>FS: Сохраняет HTML/TEX artifact
        R-->>UI: ExportResponse(url, filename, size)
    else backend недоступен
        UI->>Local: HTML preview → html2pdf.js или Blob download
    end
```

## 8. Последовательность AI-генерации LaTeX

AI-flow отделяет сбор полей, построение prompt, provider call, извлечение LaTeX, структурную validation, опциональный compile-check/repair и запись истории. Логи используют метаданные, хэши и размеры вместо полного prompt/LaTeX.

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant UI as AI modal
    participant R as generation router
    participant Prompt as prompt_builder
    participant AI as ai_generation service
    participant V as latex_validator
    participant C as LatexCompiler
    participant Hist as generation_history_service
    participant DB as Database

    U->>UI: Заполняет тему, материалы, provider/model
    UI->>R: POST /api/generation/prompt или /generate
    R->>R: rate limit + text limits
    R->>Prompt: build_generation_prompt_response(request)
    Prompt-->>R: prompt + warnings

    alt preview prompt
        R-->>UI: GenerationPromptResponse
    else generate
        R->>AI: generate(prompt, provider, model)
        AI-->>R: raw model output
        R->>R: extract_latex_code + sanitize_generated_latex_body
        R->>V: validate_latex_document(latex_code)
        V-->>R: errors/warnings/valid
        opt compile-check and repair enabled
            R->>C: compile generated document
            C-->>R: compile result
            alt compile failed and repair allowed
                R->>AI: repair prompt
                AI-->>R: repaired output
                R->>V: validate repaired LaTeX
            end
        end
        R->>Hist: record success/failure metadata
        Hist->>DB: INSERT GenerationHistory
        R-->>UI: GenerationResultResponse
        UI->>UI: Insert into current file or create generated.tex
    end
```

## 9. Состояния compile/generation задач

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> PayloadValidation: user request
    PayloadValidation --> Rejected: invalid filename/size/rate/text limit
    PayloadValidation --> Pending: accepted

    Pending --> RunningCompiler: compile/export PDF
    Pending --> RunningProvider: AI generate

    RunningCompiler --> Success: PDF/log ok
    RunningCompiler --> Failed: pdflatex error/timeout

    RunningProvider --> ValidatingLatex: raw output received
    RunningProvider --> Failed: provider unavailable/error
    ValidatingLatex --> CompileCheck: validation passed or warnings only
    ValidatingLatex --> Failed: structural validation errors
    CompileCheck --> Repairing: compile failed and repair enabled
    Repairing --> ValidatingLatex: repaired output
    CompileCheck --> Success: compile ok or check skipped
    CompileCheck --> Failed: unrepaired compile error

    Rejected --> [*]
    Success --> [*]
    Failed --> [*]
```

## 10. Развёртывание и runtime-зависимости

```mermaid
flowchart TB
    subgraph Dev["Developer machine / container"]
        Frontend["artifact: frontend/ static files"]
        subgraph ApiNode["node: FastAPI process"]
            App["artifact: backend/app/main.py"]
            Code["artifact: routers + services"]
        end
        SQLite[("database: SQLite dev DB")]
        subgraph Tex["node: TeX Live"]
            PdfLatex["artifact: pdflatex binary"]
        end
        TempDirs["artifact: runtime temp dirs"]
    end

    subgraph Prod["Production option"]
        Docker["node: Docker/Nginx"]
        Postgres[("database: PostgreSQL")]
        Queue["node: Redis/Celery scaffold"]
    end

    Frontend -->|"HTTP /api"| ApiNode
    ApiNode -->|"dev persistence"| SQLite
    ApiNode -->|"prod persistence"| Postgres
    ApiNode -->|"compile/export"| PdfLatex
    ApiNode -->|"generated artifacts"| TempDirs
    Docker -->|"reverse proxy/container runtime"| ApiNode
    Queue -.->|"future async tasks"| ApiNode
```

> Примечание: Mermaid не имеет единого стандартного `deploymentDiagram` во всех renderer-ах, поэтому deployment view намеренно оформлен как совместимый `flowchart TB` с UML-терминами `node`, `artifact` и `database` в подписях.
