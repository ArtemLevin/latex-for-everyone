# Анализ состояния сервиса Latexed и план дальнейшей разработки

Дата анализа: 2026-06-08. Репозиторий проверен по фактической структуре, Makefile-командам, backend/frontend коду, тестам, миграциям и документации.

## 1. Резюме состояния

Latexed находится на стадии **рабочего full-stack MVP / early beta**:

- есть цельный вертикальный сценарий: создать проект, редактировать `.tex` файлы, видеть локальный preview, компилировать на backend, экспортировать PDF/HTML/TEX и использовать AI-генерацию LaTeX;
- backend уже разделён на FastAPI app, routers, services, SQLAlchemy models, Pydantic schemas и Alembic migrations;
- frontend остаётся dependency-light SPA без сборки, но разделён на ordered browser scripts, которые подключаются из `frontend/main.html`;
- основные опасные границы — пользовательские LaTeX-файлы, subprocess `pdflatex`, файловые артефакты и AI-provider — уже имеют часть защит: filename policy, payload limits, sanitizer, validator, bounded compiler output и safe logging;
- тестовая база заметно выросла: текущий backend suite проходит, но покрывает в основном API/service контракты, а не полноценные browser/E2E сценарии;
- production-ready состояние ещё не достигнуто из-за отсутствия обязательной TeX Live среды в текущем окружении, недостаточной observability/readiness, синхронных тяжёлых операций, простого in-memory rate limiting и отсутствия полноценной auth/multi-user модели.

Главный вывод: проект можно демонстрировать и развивать локально, но следующий этап должен быть не добавлением большого количества новых UI-фич, а стабилизацией runtime, безопасности, эксплуатации и тестовой матрицы.

## 2. Методика анализа

Проверены следующие источники:

- структура репозитория через `rg --files` и ожидаемые директории `backend/app`, `backend/tests`, `backend/alembic`, `frontend`, `docs`;
- Makefile targets и фактические команды запуска/проверки;
- FastAPI app, routers, services, schemas, models, migrations;
- frontend shell и порядок подключения `frontend/js/*.js`;
- тесты `backend/tests/test_api.py` и fixtures AI outputs;
- ранее добавленные архитектурные диаграммы `docs/uml-diagrams.md`.

## 3. Текущая карта сервиса

### 3.1 Backend

Backend построен как FastAPI-приложение:

```text
backend/app/main.py
  → routers: projects, files, compile, export, templates, generation
  → services: project/file workflows, compiler, PDF export, AI generation, prompt builder, validator, sanitizer, cleanup
  → schemas.py: Pydantic API/service contracts
  → models.py + database.py: SQLAlchemy persistence
```

Текущие публичные группы API:

| Область | Основные endpoints | Состояние |
|---|---|---|
| Health/root | `GET /api/health`, `GET /` | Есть базовый health, но без детальной readiness по DB/compiler/storage/AI. |
| Projects | CRUD, snapshots, restore, duplicate | Работает через `ProjectService`; есть typed contracts и тесты. |
| Files | list/create/get/update/delete/upload/upload-all | Работает через `FileService`; есть защита имён и invariant единственного main-файла. |
| Templates | list/get | Статические шаблоны в router-файле; для роста лучше вынести в data/service слой. |
| Compile | project compile, raw compile, history, PDF download | Есть payload/file policy, history, typed compiler result; зависит от установленного `pdflatex`. |
| Export | PDF/HTML/TEX, download | Есть backend export и frontend fallback; PDF также зависит от `pdflatex`. |
| Generation | presets, prompt preview, validate, provider status, generate, history | Есть prompt builder, provider service, validation, compile-check/repair, token usage и persisted history. |

### 3.2 Frontend

Frontend — single-page приложение без bundler/build step:

```text
frontend/main.html
  → 01-state.js
  → 02-api.js
  → 03-init.js
  → 04-files.js
  → 05-compile-preview.js
  → 06-toolbar-view.js
  → 07-generation.js
  → 08-templates-export.js
  → 09-ui-settings.js
```

Сильные стороны:

- низкий порог запуска: достаточно статического сервера;
- есть fallback, если backend недоступен;
- CodeMirror/KaTeX/PDF.js/html2pdf.js дают редактор, preview и локальный export;
- frontend API contract частично зафиксирован backend-тестами.

Риски:

- глобальные функции и состояние усложняют безопасные изменения;
- legacy `frontend/js/main.js` удалён; риск теперь состоит в случайном повторном введении параллельного entrypoint вместо numbered scripts из `main.html`;
- нет автоматических browser/E2E тестов для основных пользовательских сценариев;
- CDN-зависимости не зафиксированы через lockfile/integrity-политику.

### 3.3 Данные и миграции

Persisted entities:

- `Project`;
- `File`;
- `CompileHistory`;
- `ProjectSnapshot`;
- `GenerationHistory`.

Состояние:

- Alembic содержит baseline schema, generation history и token usage migration;
- локальный `AUTO_CREATE_TABLES=true` удобен для dev, но production должен запускаться с `AUTO_CREATE_TABLES=false` и явными миграциями;
- есть compatibility patch для старых локальных `generation_history` таблиц без token columns.

### 3.4 Runtime-зависимости

Обязательные/важные зависимости:

- Python/uv/FastAPI/SQLAlchemy/Pydantic;
- Node только для `node --check` frontend scripts;
- `pdflatex` и Russian/T2A support для полноценной backend-компиляции и PDF export;
- AI provider: локальный Ollama или OpenAI-compatible provider;
- SQLite по умолчанию, PostgreSQL как production path;
- Docker/Nginx config уже присутствует.

## 4. Фактические результаты проверок

| Проверка | Результат | Комментарий |
|---|---:|---|
| Layout verification | PASS | Ожидаемые backend/frontend/docs директории существуют. |
| `make compileall` | PASS | Python-файлы backend компилируются без syntax errors. |
| `make frontend-check` | PASS | Актуальные numbered frontend scripts проходят `node --check`; legacy `main.js` удалён. |
| `make test` | PASS | `88 passed`; есть `110 warnings`. |
| `make latex-check` | FAIL из-за окружения | `pdflatex not found`; это блокирует реальную backend-компиляцию/PDF export в текущей среде, но не доказывает дефект кода. |

Заметные warnings:

- `pytest-asyncio` предупреждает, что `asyncio_default_fixture_loop_scope` не задан;
- SQLAlchemy/Python предупреждают о `datetime.datetime.utcnow()`; стоит перейти на timezone-aware UTC timestamps.

## 5. Сильные стороны проекта

1. **Цельный пользовательский workflow.** Есть frontend editor, file tree, preview, compile, export и AI generation.
2. **Неплохие service boundaries.** Projects/files уже делегируют в сервисы; compile/export/AI имеют отдельные service modules.
3. **Безопасность LaTeX boundary уже начата.** Есть filename allowlist, path traversal checks, payload limits, compiler output truncation, sanitizer и validator.
4. **AI-flow не ограничен простым provider call.** Есть prompt preview, presets, provider status, validation, compile-check/repair, token usage и history.
5. **Миграционный путь существует.** Alembic уже в репозитории, есть несколько revisions и тест baseline schema.
6. **Документация для разработки становится системной.** Есть architecture boundaries, references, prompting guide, agent workflow и UML/Mermaid обзор.

## 6. Основные проблемы и риски

### P0 — блокеры production-readiness

1. **Нет гарантированной TeX runtime среды вне Docker.** Без `pdflatex` backend compile/export PDF не работают; `make latex-check` сейчас падает в текущем окружении.
2. **Тяжёлые операции выполняются синхронно.** Компиляция, export PDF и AI generation могут занимать секунды/минуты и держать HTTP request open.
3. **Rate limiting in-memory.** Лимиты не будут корректно работать при нескольких процессах/репликах и не переживают restart.
4. **Нет полноценной auth/ownership модели.** В моделях есть `owner_id`, но API сейчас фактически работает как single-user/local editor.
5. **Readiness/observability недостаточны.** Health показывает базовый статус, но не проверяет DB migrations, compiler availability, writable artifact dirs и AI provider readiness.

### P1 — высокие риски качества и безопасности

1. **LaTeX sandboxing требует усиления.** Нужна явная политика `pdflatex` flags, shell escape, temp dirs, UID/container isolation, TTL cleanup и максимально разрешённые расширения.
2. **Frontend без E2E покрытия.** Критичные пользовательские flows не проверяются автоматическим браузерным тестом.
3. **Frontend entrypoint drift.** Legacy `frontend/js/main.js` удалён; порядок numbered scripts нужно защищать contract-тестами, чтобы не появился параллельный entrypoint.
4. **Большой `generation.py`.** Router содержит почти 500 строк и смешивает HTTP, orchestration, logging, repair flow и history handling; часть логики можно вынести в service layer.
5. **Templates лежат в router.** При росте шаблонов лучше перейти к data file/service, чтобы router не был контейнером данных.

### P2 — улучшения поддерживаемости

1. **Timezone-aware timestamps.** Нужно заменить `datetime.utcnow()` на `datetime.now(UTC)` и синхронизировать миграции/тесты.
2. **OpenAPI/contract docs.** API есть, но пользовательская документация endpoints ограничена.
3. **Frontend dependency policy.** CDN versions есть, но нет SRI/integrity или локального vendor strategy.
4. **Storage abstraction.** Сейчас артефакты локальные; production может потребовать S3-compatible storage или volume policy.

## 7. Рекомендуемый план разработки

### Этап 0. Стабилизация baseline, 1–2 дня

**Цель:** зафиксировать текущее состояние и убрать неоднозначности.

- Обновить README/docs: явно описать, что `pdflatex` обязателен для backend compile/export, а без него доступен frontend fallback.
- Поддерживать contract test, подтверждающий, что `main.html` использует только numbered scripts и legacy `frontend/js/main.js` не возвращается.
- Добавить в CI или локальный checklist команды: `make compileall`, `make frontend-check`, `make test`, `make latex-check` как optional environment check.
- Завести простой release checklist: migrations, env vars, compiler check, artifact cleanup, smoke health.

**Definition of Done:** разработчик за 10 минут понимает, как поднять сервис, какие flows работают без TeX Live, а какие требуют `pdflatex`.

### Этап 1. Production runtime hardening, 1 неделя

**Цель:** сделать compile/export безопаснее и предсказуемее.

- Формализовать `pdflatex` command policy: `-interaction=nonstopmode`, `-halt-on-error`, no shell escape, bounded working directory, bounded log output.
- Усилить artifact lifecycle: периодический cleanup по `ARTIFACT_TTL_SECONDS`, тесты на safe deletion, отдельные directories для compile/export/upload.
- Добавить readiness endpoint, например `GET /api/ready`, который проверяет DB connection, migrations state, compiler availability и writable artifact dirs.
- Расширить download hardening: единый helper для safe artifact filename/type validation между compile/export.
- Добавить operational docs для Docker и non-Docker TeX Live установки.

**Definition of Done:** backend честно сообщает, готов ли он компилировать/export PDF, и не пишет/читает пользовательские файлы вне разрешённых runtime директорий.

### Этап 2. Асинхронные jobs для тяжёлых операций, 1–2 недели

**Цель:** убрать долгие compile/export/generation из синхронного request lifecycle.

- Спроектировать job model: `Job(id, type, status, project_id, input_ref, result_ref, error, created_at, updated_at)`.
- Начать с compile jobs: `POST /api/compile/jobs`, `GET /api/compile/jobs/{id}`, download result по готовности.
- Переиспользовать существующий Celery/Redis scaffold или сделать минимальный DB-backed worker, если Celery пока избыточен.
- Сохранить текущие synchronous endpoints как compatibility layer на переходный период.
- Добавить frontend polling/progress UI и cancellation UX.

**Definition of Done:** длительные операции не держат HTTP request до завершения, frontend показывает статус и результат задачи.

### Этап 3. Auth, ownership и multi-user режим, 1–2 недели

**Цель:** перейти от local/single-user модели к сервисной модели.

- Определить минимальную модель пользователя и ownership policy.
- Связать `Project.owner_id` с реальным user entity или внешним identity provider.
- Ограничить доступ к projects/files/snapshots/history по владельцу.
- Добавить tests на cross-user access denial.
- Обновить frontend bootstrap: anonymous/local mode vs authenticated mode.

**Definition of Done:** данные одного пользователя нельзя читать/изменять через ID другого пользователя.

### Этап 4. Тестовая матрица frontend и E2E, 1 неделя

**Цель:** покрыть критичные browser flows.

- Добавить Playwright или аналогичный минимальный E2E слой.
- Smoke scenarios:
  - открыть `main.html`;
  - создать проект из шаблона;
  - создать/переименовать/удалить файл;
  - отредактировать main `.tex`;
  - выполнить local preview;
  - выполнить compile при доступном backend или проверить graceful fallback;
  - открыть AI modal и проверить prompt preview mock.
- Добавить contract tests для frontend payloads там, где backend shape критичен.

**Definition of Done:** ключевой frontend workflow проверяется автоматически, а не только `node --check`.

### Этап 5. AI pipeline refinement, 1–2 недели

**Цель:** сделать AI generation стабильнее и дешевле сопровождать.

- Вынести orchestration из `generation.py` в отдельный service: generate → extract → validate → compile-check → repair → history.
- Сделать provider interface явным: Ollama, OpenAI-compatible, mock provider для tests.
- Улучшить token usage: использовать реальные provider usage fields, где доступны, и fallback estimation.
- Добавить replay/debug режим по `GenerationHistory`, не раскрывая полный prompt/user content в логах.
- Документировать safe/rich LaTeX mode и insertion modes для пользователей.

**Definition of Done:** router остаётся HTTP-слоем, AI orchestration тестируется как service без TestClient там, где это возможно.

### Этап 6. Product polish и документация, постоянно

**Цель:** сделать сервис понятным для пользователей и сопровождающих.

- Разделить docs для пользователей, операторов и разработчиков.
- Добавить API examples для compile/export/generation.
- Улучшить ошибки frontend: actionable messages для missing TeX Live, provider unavailable, invalid LaTeX.
- Добавить monitoring guide: logs, request IDs, slow requests, artifact cleanup metrics.
- Подготовить roadmap releases: `0.1 local MVP`, `0.2 hardened compile/export`, `0.3 async jobs`, `0.4 multi-user beta`.

## 8. Приоритетный backlog

| Priority | Item | Почему важно | Проверка готовности |
|---|---|---|---|
| P0 | Документировать и автоматизировать TeX Live readiness | Без этого compile/export PDF непредсказуемы | `make latex-check` PASS в целевой среде; `/api/ready` сообщает compiler status |
| P0 | Readiness endpoint | Нужно отделить live от ready | Tests на DB/compiler/storage readiness branches |
| P0 | Async compile job prototype | Убирает долгие HTTP requests | API + frontend polling smoke test |
| P0 | Artifact cleanup policy | Не копить PDF/TEX/HTML и не отдавать лишнее | Unit tests cleanup + docs TTL |
| P1 | E2E smoke tests | Защита frontend workflow | Playwright smoke в CI/local target |
| P1 | Guard frontend script order | Уменьшает риск повторного появления неподключаемого entrypoint | `main.html` script order test; legacy `main.js` отсутствует |
| P1 | Move AI orchestration to service | Поддерживаемость и unit testing | `generation.py` меньше, service tests больше |
| P1 | Distributed rate limiting | Production multi-replica | Redis-backed limiter или documented single-process limitation |
| P1 | Auth/ownership | Безопасность пользовательских данных | Cross-user denial tests |
| P2 | Timezone-aware datetimes | Убрать deprecation и timezone ambiguity | Tests без `utcnow()` warnings |

## 9. Ближайший план разработки

Ближайший план сфокусирован на **стабилизации сервиса перед расширением функциональности**. Новые пользовательские возможности стоит добавлять только после того, как compile/export runtime, диагностика окружения и базовые regression checks станут предсказуемыми.

### 9.1 Цель ближайшего спринта

За 1–2 недели довести Latexed до состояния, в котором разработчик или оператор может быстро ответить на четыре вопроса:

1. Готов ли backend обслуживать API и работать с базой данных?
2. Готов ли runtime выполнять backend-компиляцию LaTeX и PDF export?
3. Безопасно ли сервис создаёт, хранит, чистит и отдаёт compile/export артефакты?
4. Защищены ли ключевые frontend/backend сценарии минимальными автоматическими проверками?

### 9.2 Workstream A — readiness и диагностика окружения

- **Приоритет:** P0
- **Оценка:** 2–3 дня
- **Владелец зоны:** backend/runtime

Задачи:

- Добавить endpoint `GET /api/ready` рядом с текущим `GET /api/health`.
- Проверять в readiness:
  - доступность DB connection;
  - наличие ожидаемых таблиц или Alembic head/version state;
  - наличие `pdflatex` в `PATH`;
  - доступность Russian/T2A LaTeX support через `kpsewhich`, если бинарь есть;
  - доступность на запись runtime directories для compile/export/upload artifacts.
- Разделить понятия:
  - `health` — процесс жив и может отвечать HTTP;
  - `ready` — сервис готов выполнять заявленные функции.
- Добавить backend tests для successful readiness и degraded readiness без `pdflatex`.
- Обновить README: объяснить, какие функции работают без TeX Live, а какие требуют `make latex-check`.

Definition of Done:

- `GET /api/ready` возвращает структурированный JSON со статусами `database`, `compiler`, `latex_packages`, `artifact_dirs`.
- Отсутствие `pdflatex` не маскируется: endpoint явно показывает degraded state.
- Tests покрывают минимум один успешный и один degraded сценарий.

#### 9.2.1 Детальный план реализации итерации 1

**Целевой API-контракт `GET /api/ready`:**

```json
{
  "status": "ready | degraded | not_ready",
  "checks": {
    "database": {
      "status": "ok | error",
      "message": "DB connection is available",
      "details": {"required_tables_present": true}
    },
    "compiler": {
      "status": "ok | missing | error",
      "message": "pdflatex found",
      "details": {"binary": "pdflatex", "path": "/usr/bin/pdflatex"}
    },
    "latex_packages": {
      "status": "ok | skipped | missing | error",
      "message": "Russian/T2A support is available",
      "details": {"russian_ldf": true, "t2aenc_def": true}
    },
    "artifact_dirs": {
      "status": "ok | error",
      "message": "Runtime directories are writable",
      "details": {"compile_work_dir": "ok", "upload_dir": "ok"}
    }
  }
}
```

Итоговый `status` считать так:

- `ready` — все обязательные проверки `ok`, а package checks либо `ok`, либо осознанно `skipped` только если compiler недоступен;
- `degraded` — API и DB доступны, но отсутствует `pdflatex` или LaTeX packages; frontend/local flows могут работать, backend compile/export PDF — нет;
- `not_ready` — недоступна DB, отсутствуют обязательные таблицы или runtime directories не writable.

**Изменяемые файлы:**

- `backend/app/schemas.py` — добавить typed response-схемы readiness, например `ReadinessCheckResponse` и `ReadinessResponse`.
- `backend/app/services/readiness.py` — новый сервис с чистыми функциями проверки DB, compiler, packages и artifact dirs.
- `backend/app/main.py` — добавить endpoint `GET /api/ready`; оставить `GET /api/health` лёгким liveness endpoint без тяжёлых проверок.
- `backend/tests/test_api.py` или `backend/tests/test_readiness.py` — добавить успешный и degraded сценарии через `TestClient` и monkeypatch.
- `README.md` — добавить короткий раздел про `health` vs `ready`, TeX Live requirement и `make latex-check`.
- `docs/references.md` — при необходимости обновить reference для health/readiness поведения.

**Порядок работ по дням:**

1. **День 1 — API contract и сервисные проверки.**
   - Добавить Pydantic-схемы readiness response.
   - Реализовать `check_database_ready(db_or_engine)`: `SELECT 1`, inspection required tables `projects`, `files`, `compile_history`, `project_snapshots`, `generation_history`.
   - Реализовать `check_compiler_ready()`: `shutil.which(settings.LATEX_COMPILER)` без запуска пользовательского LaTeX.
   - Реализовать `check_latex_packages_ready()`: если compiler missing, вернуть `skipped`; иначе проверить `kpsewhich russian.ldf` и `kpsewhich t2aenc.def` с коротким timeout.
   - Реализовать `check_artifact_dirs_ready()`: существование и запись в `settings.COMPILE_WORK_DIR` и `settings.UPLOAD_DIR` через безопасный временный probe-файл.

2. **День 2 — endpoint, тесты и degraded semantics.**
   - Подключить `GET /api/ready` в `backend/app/main.py`.
   - Не менять поведение `GET /api/health`: он должен оставаться быстрым liveness endpoint.
   - Добавить tests:
     - `test_readiness_ready_when_all_checks_pass` с monkeypatch для compiler/package checks;
     - `test_readiness_degraded_when_pdflatex_missing` с `shutil.which -> None`;
     - `test_readiness_not_ready_when_database_check_fails` или artifact directory not writable;
     - schema/assertions на наличие top-level `status` и ключей `database`, `compiler`, `latex_packages`, `artifact_dirs`.
   - Проверить, что ошибки readiness не логируют пользовательский LaTeX или secrets.

3. **День 3 — документация и polish.**
   - Обновить README: `GET /api/health` = процесс жив, `GET /api/ready` = среда готова к DB/compile/export.
   - Явно описать, что без TeX Live доступны frontend local preview, базовый CRUD и prompt/validation flows, но backend compile/export PDF будут degraded.
   - Добавить пример `curl http://localhost:8000/api/ready` и рекомендацию `make latex-check`.
   - Запустить проверки и обновить план, если implementation выявит новые ограничения.

**Тестовая матрица итерации 1:**

| Сценарий | Ожидаемый результат | Как проверять |
|---|---|---|
| DB ok, compiler ok, packages ok, dirs writable | `status=ready` | `TestClient` + monkeypatch внешних бинарей |
| DB ok, `pdflatex` missing | `status=degraded`, `compiler.status=missing`, `latex_packages.status=skipped` | monkeypatch `shutil.which` |
| DB ok, compiler ok, `russian.ldf` или `t2aenc.def` missing | `status=degraded`, package detail указывает missing dependency | monkeypatch subprocess/kpsewhich helper |
| DB unavailable или required tables missing | `status=not_ready`, `database.status=error` | monkeypatch DB check/service |
| Runtime dir not writable | `status=not_ready`, `artifact_dirs.status=error` | `tmp_path`/monkeypatch settings |
| `/api/health` | всегда быстрый liveness без compiler/package probes | existing health test + assertion shape |

**Команды проверки перед завершением итерации:**

```bash
make compileall
make test
make latex-check  # optional/environment check: может быть warning, если pdflatex отсутствует
```

Если меняется README/docs без Python-кода, достаточно `git diff --check`; если меняется endpoint или service, обязательны `make compileall` и `make test`.

### 9.3 Workstream B — hardening compile/export артефактов

- **Приоритет:** P0
- **Оценка:** 2–3 дня
- **Владелец зоны:** backend/security

Задачи:

- Вынести общую проверку имён download-артефактов в единый helper/service для compile и export.
- Зафиксировать allowlist типов download-файлов: PDF, TEX, HTML и только ожидаемые generated filenames.
- Проверить, что compile/export не читают файлы вне разрешённых output directories.
- Уточнить lifecycle артефактов:
  - TTL через `ARTIFACT_TTL_SECONDS`;
  - cleanup command/target;
  - запрет удаления файлов вне runtime directories.
- Добавить тесты на path traversal, неподдерживаемые расширения, старые файлы и сохранение новых файлов.

Definition of Done:

- Compile/export download endpoints используют общий safe-path механизм.
- Cleanup покрыт тестами и не может удалить файлы вне разрешённых директорий.
- Документация объясняет, где лежат runtime artifacts и как их чистить.

#### 9.3.1 Детальный план реализации итерации 2

**Текущая точка старта:**

- `compile.py` уже проверяет, что download filename заканчивается на `.pdf` и не содержит path components, но эта проверка локальна для compile router.
- `export.py` уже имеет `resolve_export_download_path()`, suffix allowlist и `resolve()`-prefix check для export artifacts, но это не переиспользуется compile endpoint.
- `artifact_cleanup.cleanup_old_files()` удаляет старые файлы по suffix allowlist внутри переданной директории, но не знает о доверенных runtime roots.
- `make clean-artifacts` сейчас чистит default `/tmp` директории напрямую; для production-safe поведения лучше иметь Python cleanup entrypoint, использующий тот же safe cleanup service.

**Целевой дизайн safe artifact service:**

Создать единый backend service, например `backend/app/services/artifact_paths.py`, который отвечает за:

- описание artifact roots:
  - compile PDF root: `Path(settings.COMPILE_WORK_DIR) / "pdfs"`;
  - export root: `Path(settings.UPLOAD_DIR) / "exports"`;
- allowlist типов:
  - compile download: только `.pdf`, media type `application/pdf`, inline disposition;
  - export download: `.pdf`, `.html`, `.zip`; если нужен raw `.tex` download в будущем — добавить явно, а не через wildcard;
- валидацию имени:
  - `Path(filename).name == filename`;
  - отсутствие `/`, `\`, `..`, пустого имени, control characters;
  - suffix входит в allowlist конкретного artifact kind;
  - опционально prefix/pattern generated filenames, например `compiled_*.pdf`, `export_*.pdf`, `export_*.html`, `export_*.zip`, если текущие generator filenames уже стабильны;
- безопасное построение пути:
  - `root.resolve()` и `(root / filename).resolve()`;
  - проверка, что итоговый путь находится внутри root;
  - запрет follow-out через symlink escape;
- единый typed result, например `ArtifactDownloadTarget(path, filename, media_type, content_disposition_type)`.

**Изменяемые файлы:**

- `backend/app/services/artifact_paths.py` — новый service/helper для safe path resolution и artifact kind allowlists.
- `backend/app/services/artifact_cleanup.py` — расширить cleanup так, чтобы он принимал только доверенные roots или валидировал root через общий helper; сохранить простую функцию для unit tests, если она полезна.
- `backend/app/routers/compile.py` — заменить локальную проверку filename на общий service для compile PDF download.
- `backend/app/routers/export.py` — заменить `resolve_export_download_path()` на общий service; удалить дублирующий локальный resolver.
- `backend/app/services/latex_compiler.py` и `backend/app/services/pdf_generator.py` — проверить, что cleanup вызывается только для разрешённых output dirs и suffixes.
- `Makefile` — заменить или дополнить `clean-artifacts` безопасной Python-командой, не использующей широкий `rm -rf`, если это возможно без усложнения.
- `README.md` — уточнить расположение compile/export/upload artifacts, TTL и команду очистки.
- `backend/tests/test_api.py` или отдельный `backend/tests/test_artifacts.py` — добавить unit/API tests для resolver, downloads и cleanup.

**Порядок работ по дням:**

1. **День 1 — общий safe-path service.**
   - Описать artifact kinds: `compile_pdf`, `export_pdf`, `export_html`, `export_zip` или агрегированно `compile`/`export` с per-suffix media map.
   - Реализовать `resolve_artifact_download(kind, filename)` без HTTP-зависимостей; ошибки — доменные exceptions, которые routers переводят в `HTTPException`.
   - Покрыть unit tests:
     - valid compile PDF;
     - valid export PDF/HTML/ZIP;
     - path traversal `../file.pdf`, `nested/file.pdf`, URL-encoded traversal, backslash traversal;
     - unsupported extension `.txt`, `.tex` для download, если `.tex` не является текущим downloadable artifact;
     - symlink или resolved path escape, если это практично протестировать в `tmp_path`.

2. **День 2 — интеграция в endpoints и cleanup lifecycle.**
   - Подключить общий resolver в `download_compiled_pdf()` и `download_export()`.
   - Сохранить текущие response semantics: invalid filename/type → `400`, missing file → `404`, successful file → `FileResponse` с правильным media type.
   - Уточнить cleanup service:
     - cleanup работает только внутри разрешённого root;
     - удаляет только файлы с allowlisted suffixes;
     - не удаляет директории, symlinks-out, свежие файлы и неизвестные расширения;
     - respect `ARTIFACT_TTL_SECONDS <= 0` как disabled cleanup.
   - Добавить tests на старые и новые файлы: старый allowed artifact удаляется, свежий allowed artifact остаётся, unsupported file остаётся.

3. **День 3 — CLI/Makefile, документация и regression.**
   - Добавить безопасный script entrypoint, например `backend/scripts/clean_artifacts.py`, или Makefile target через `uv run python -m app...`, если package import path удобен.
   - Обновить `make clean-artifacts`, чтобы он вызывал безопасный cleanup, либо явно документировать, что target предназначен только для default local `/tmp` directories.
   - Обновить README runtime artifacts section:
     - compile PDFs: `${COMPILE_WORK_DIR}/pdfs`;
     - export files: `${UPLOAD_DIR}/exports`;
     - uploads: `${UPLOAD_DIR}`;
     - TTL: `ARTIFACT_TTL_SECONDS`;
     - cleanup command and limitations.
   - Запустить проверки и убедиться, что public download URLs не изменились.

**Тестовая матрица итерации 2:**

| Сценарий | Ожидаемый результат | Уровень теста |
|---|---|---|
| Compile download valid generated PDF | `200`, `application/pdf`, inline response | API/TestClient |
| Compile download `../x.pdf` или `nested/x.pdf` | `400` | API/TestClient + unit resolver |
| Compile download unsupported suffix | `400` | API/TestClient |
| Export download valid `.pdf`, `.html`, `.zip` | `200` и корректный media type | API/TestClient |
| Export download unsupported suffix `.txt`/unexpected `.tex` | `400` | API/TestClient |
| Resolved path escapes artifact root | `400` или domain validation error | Unit resolver |
| Missing but valid artifact filename | `404` | API/TestClient |
| Cleanup старого allowed artifact | файл удалён, count увеличен | Unit cleanup |
| Cleanup свежего allowed artifact | файл остаётся | Unit cleanup |
| Cleanup unsupported suffix или nested directory | объект остаётся | Unit cleanup |
| Cleanup outside trusted root | операция запрещена или не выполняется | Unit cleanup |

**Acceptance checklist для PR итерации 2:**

- [ ] В compile и export download endpoints нет собственной ручной path/suffix логики; они используют общий artifact service.
- [ ] Allowlist расширений и media types находится в одном месте.
- [ ] Все path operations используют `Path.resolve()` и root containment check.
- [ ] Cleanup не использует пользовательский путь без проверки trusted root.
- [ ] `make clean-artifacts` безопасен для локального использования или явно перенаправлен на safe cleanup script.
- [ ] README описывает директории, TTL и команду cleanup.
- [ ] Пройдены `make compileall` и `make test`; `make latex-check` выполняется как environment check, если требуется проверить реальный TeX runtime.

**Команды проверки перед завершением итерации:**

```bash
make compileall
make test
make latex-check  # optional/environment check for real TeX runtime
```

Если меняется только документация планирования, достаточно `git diff --check`; при реализации service/router/tests обязательны `make compileall` и `make test`.

### 9.4 Workstream C — frontend regression baseline

- **Приоритет:** P1
- **Оценка:** 2–4 дня
- **Владелец зоны:** frontend/testing

Задачи:

- Зафиксировать, что legacy `frontend/js/main.js` удалён и не должен возвращаться как параллельный entrypoint.
- Добавить contract test, который проверяет фактический script order в `frontend/main.html`:
  `01-state.js → 02-api.js → ... → 09-ui-settings.js`.
- Добавить минимальный E2E smoke на Playwright или аналогичном инструменте:
  - открыть `main.html`;
  - убедиться, что редактор и file tree отображаются;
  - изменить содержимое main file;
  - выполнить local preview;
  - проверить graceful fallback, если backend или `pdflatex` недоступны.
- Не вводить bundler на этом этапе, чтобы не смешивать hardening и frontend build migration.

Definition of Done:

- `make frontend-check` остаётся зелёным.
- Есть хотя бы один browser smoke сценарий для локального editor/preview workflow.
- Разработчик не может случайно править неподключаемый frontend entrypoint, не заметив этого.

#### 9.4.1 Детальный план реализации итерации 3

**Текущая точка старта:**

- `frontend/main.html` подключает только numbered scripts `01-state.js` → `09-ui-settings.js`; legacy `frontend/js/main.js` удалён.
- `make frontend-check` запускает `node --check` для актуальных файлов `frontend/js/*.js`, а contract tests защищают порядок подключения scripts.
- Frontend не имеет browser/E2E тестов; текущая защита — syntax check и отдельные backend contract tests.
- Backend для базового local preview не обязателен: frontend должен graceful fallback при недоступном backend или отсутствии `pdflatex`.

**Решение по `frontend/js/main.js`:**

Legacy bundle удалён как неподключаемый entrypoint. Дальнейшие изменения должны вноситься только в numbered scripts, подключённые из `frontend/main.html`. Если кто-то попытается вернуть `js/main.js`, contract test должен упасть и потребовать явного архитектурного решения.

**Целевой contract test для script order:**

Добавить тест, который парсит `frontend/main.html` и проверяет точный список локальных scripts:

```text
js/01-state.js
js/02-api.js
js/03-init.js
js/04-files.js
js/05-compile-preview.js
js/06-toolbar-view.js
js/07-generation.js
js/08-templates-export.js
js/09-ui-settings.js
```

Тест должен также проверять, что `js/main.js` не подключён. Возможные места:

- `backend/tests/test_api.py` как простой file-contract test без browser;
- лучше — новый `backend/tests/test_frontend_contract.py`, чтобы отделить frontend contracts от API tests.

**Минимальный E2E smoke design:**

Предпочтительный инструмент — Playwright, но вводить его нужно минимально и без bundler:

- добавить dev dependency или отдельную npm/pytest команду только для E2E;
- добавить Makefile target, например `make frontend-e2e`;
- поднимать static frontend server через `python -m http.server` или Playwright `webServer`;
- backend можно не поднимать для первого smoke: проверить offline/local fallback path.

Минимальный smoke сценарий:

1. Открыть `http://localhost:<port>/main.html`.
2. Дождаться загрузки редактора CodeMirror и file tree.
3. Проверить, что виден `main.tex` или базовый файл проекта.
4. Ввести/заменить содержимое редактора на минимальный LaTeX документ.
5. Запустить local preview или действие, которое приводит к preview render без backend.
6. Проверить, что UI не падает, показывает preview/status и корректно сообщает о backend fallback/degraded state.
7. Не требовать `pdflatex` для этого smoke; реальная backend compile проверяется отдельными backend/runtime checks.

**Изменяемые файлы:**

- `frontend/js/main.js` — удалён; contract tests должны не дать вернуть его незаметно.
- `frontend/main.html` — не менять script order без необходимости; если меняется, обновить contract test и docs.
- `backend/tests/test_frontend_contract.py` или `backend/tests/test_api.py` — добавить script-order contract test.
- `pyproject.toml` или отдельный frontend test config — добавить Playwright/pytest-playwright только если выбран Python E2E путь.
- `Makefile` — добавить `frontend-e2e` и, возможно, включить его в отдельный optional target, но не в `make check` до стабилизации окружения.
- `README.md` — описать, как запускать frontend smoke и что он проверяет.
- `docs/references.md` — обновить предупреждение о script order и статусе legacy entrypoint.

**Порядок работ по дням:**

1. **День 1 — legacy entrypoint и contract test.**
   - Подтвердить, что legacy `frontend/js/main.js` отсутствует.
   - Добавить script-order contract test для `frontend/main.html`.
   - Обновить `make frontend-check`, если удаление `main.js` меняет список JS files автоматически через wildcard.
   - Запустить `make frontend-check` и `make test`.

2. **День 2 — E2E smoke foundation.**
   - Выбрать инструмент:
     - Playwright Python, если хотим держать проверки в `uv`/pytest ecosystem;
     - Playwright Node, если удобнее изолировать browser tests от backend pytest.
   - Добавить минимальную конфигурацию без bundler.
   - Реализовать первый smoke для offline/local editor path.
   - Добавить Makefile target `frontend-e2e` или `e2e-frontend`.
   - Документировать, если browser binaries требуют отдельной установки (`playwright install`).

3. **День 3–4 — стабилизация селекторов и fallback assertions.**
   - Убрать хрупкие selectors: предпочитать стабильные IDs/classes из `main.html`.
   - Проверить graceful fallback без backend: не должно быть uncaught JS errors, критичные controls остаются доступны.
   - Добавить минимальные assertions на editor, file tree и preview/status.
   - Обновить docs и убедиться, что E2E можно пропускать/помечать warning в окружениях без browser dependencies.

**Тестовая матрица итерации 3:**

| Сценарий | Ожидаемый результат | Уровень теста |
|---|---|---|
| `main.html` подключает numbered scripts в правильном порядке | exact list совпадает с ожидаемым | Contract/unit test |
| `frontend/js/main.js` не подключён | test явно падает, если `js/main.js` добавили обратно без решения | Contract/unit test |
| `make frontend-check` | PASS для актуальных frontend scripts | Command check |
| Browser открывает `main.html` | страница загружается без uncaught JS errors | E2E smoke |
| Editor visible | CodeMirror/editor container доступен | E2E smoke |
| File tree visible | sidebar/file tree содержит стартовый файл | E2E smoke |
| Изменение main file | текст в editor меняется и состояние не ломается | E2E smoke |
| Local preview/fallback | preview/status обновляется без backend/`pdflatex` | E2E smoke |
| Backend недоступен | UI показывает fallback/degraded поведение, а не fatal error | E2E smoke |

**Acceptance checklist для PR итерации 3:**

- [ ] Legacy `frontend/js/main.js` отсутствует и защищён contract test-ом от незаметного возврата.
- [ ] Есть automated contract test на script order в `frontend/main.html`.
- [ ] Есть минимум один browser smoke для local editor/preview workflow.
- [ ] E2E не требует `pdflatex` и не зависит от запущенного backend для базового сценария.
- [ ] `make frontend-check` проходит.
- [ ] README/docs объясняют, как запускать frontend smoke и какие зависимости нужны.
- [ ] Bundler/framework migration не начат в этом PR.

**Команды проверки перед завершением итерации:**

```bash
make frontend-check
make test
make frontend-e2e  # optional, если target добавлен и browser dependencies доступны
```

Если E2E не может установиться в CI/local среде из-за browser dependencies, это фиксируется как environment limitation; contract test и `make frontend-check` всё равно должны проходить.

### 9.5 Workstream D — cleanup warnings и developer confidence

- **Приоритет:** P1
- **Оценка:** 1–2 дня
- **Владелец зоны:** backend/testing

Задачи:

- Задать `asyncio_default_fixture_loop_scope` в pytest configuration.
- Заменить новые/текущие `datetime.utcnow()` на timezone-aware UTC helper, например `datetime.now(UTC)`.
- Проверить, что миграции и response schemas не ломаются от timezone-aware значений.
- Зафиксировать warning budget: тесты не должны бесконтрольно накапливать новые warnings.

Definition of Done:

- `make test` проходит с существенно меньшим числом warnings.
- Новые timestamps создаются через единый timezone-aware подход.
- Тесты явно показывают, какие warnings ещё допустимы временно.

#### 9.5.1 Детальный план реализации итерации 4

**Текущая точка старта:**

- `make test` проходит, но создаёт заметный шум warnings: pytest-asyncio предупреждает о неявном fixture loop scope, а SQLAlchemy/Python предупреждают о `datetime.datetime.utcnow()`.
- `pyproject.toml` уже содержит `[tool.pytest.ini_options]`, поэтому настройку `asyncio_default_fixture_loop_scope` лучше добавить туда, без отдельного `pytest.ini`.
- `datetime.utcnow()` используется в SQLAlchemy model defaults и service-level ручных обновлениях timestamps.
- Миграции сейчас создают `DateTime` columns без timezone-aware политики; нужно выбрать совместимую стратегию, чтобы не сломать SQLite tests и существующие response schemas.

**Целевой подход к UTC timestamps:**

- Добавить единый helper, например `backend/app/services/time_utils.py` или `backend/app/time_utils.py`:

```python
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
```

- Для SQLAlchemy defaults использовать callable `utc_now`, а не результат вызова.
- Для ручных обновлений `updated_at` использовать тот же helper.
- Не смешивать `datetime.utcnow()` и `datetime.now(UTC)` в новом коде.
- Если текущие DB columns остаются `DateTime` без `timezone=True`, явно проверить сериализацию Pydantic/FastAPI и SQLite compatibility. Если timezone-aware значения вызывают несовместимость, принять промежуточную стратегию:
  - helper возвращает timezone-aware UTC на service/API boundary;
  - DB сохраняет compatible UTC-naive только через отдельный helper `utc_now_naive()`;
  - решение обязательно документируется, чтобы не было скрытого смешения.

**Изменяемые файлы:**

- `pyproject.toml` — добавить `asyncio_default_fixture_loop_scope = "function"` или другой явно выбранный scope в `[tool.pytest.ini_options]`.
- `backend/app/models.py` — заменить `datetime.utcnow` в defaults/onupdate на единый helper.
- `backend/app/services/project_service.py` — заменить ручные `datetime.utcnow()` для `updated_at`.
- `backend/app/services/file_service.py` — заменить ручные `datetime.utcnow()` для `updated_at`.
- `backend/tests/test_api.py` или отдельный test-файл — добавить regression tests на timestamp serialization и отсутствие прямого `datetime.utcnow()` в app code.
- `PLAN.md`/README/docs — при необходимости зафиксировать timestamp policy и warning budget.

**Порядок работ по дням:**

1. **День 1 — pytest config и timestamp helper.**
   - Добавить `asyncio_default_fixture_loop_scope` в `pyproject.toml`.
   - Создать единый UTC helper.
   - Заменить `datetime.utcnow()` в `models.py`, `project_service.py`, `file_service.py`.
   - Запустить targeted search: `rg -n "datetime\.utcnow|utcnow" backend/app backend/tests`.
   - Запустить `make compileall` и `make test`, сравнить количество warnings с baseline.

2. **День 2 — schema/migration compatibility и warning budget.**
   - Проверить, что API responses с `created_at`/`updated_at` по-прежнему сериализуются корректно для projects/files/history/snapshots/generation history.
   - Проверить Alembic baseline/autogenerated schema expectations: изменение Python callable defaults не должно требовать DB migration, если тип columns не меняется.
   - Добавить regression test, который создаёт/обновляет project/file и проверяет timestamp fields в JSON response.
   - Добавить warning budget в pytest config или test workflow:
     - сначала зафиксировать known allowed warnings через `filterwarnings`, если они сторонние;
     - для app warnings стремиться к нулю;
     - не скрывать новые warnings широким `ignore::Warning`.
   - Обновить документацию для developers: новые timestamps — только через helper.

**Warning budget policy:**

- Разрешены только явно перечисленные временные warnings от внешних библиотек, если их нельзя быстро устранить.
- Запрещён широкий global ignore всех warnings.
- App-level deprecation warnings должны устраняться, а не подавляться.
- PR должен показывать baseline до/после: например, было около `110 warnings`, стало существенно меньше; остаток описан в PR/testing notes.

**Тестовая матрица итерации 4:**

| Сценарий | Ожидаемый результат | Уровень теста |
|---|---|---|
| pytest config содержит explicit asyncio loop scope | pytest-asyncio warning исчезает | `make test` output/config test |
| App code не содержит `datetime.utcnow()` | `rg` не находит usage в `backend/app` | command check или regression test |
| Создание project/file | `created_at` и `updated_at` присутствуют и сериализуются | API/TestClient |
| Обновление project/file | `updated_at` обновляется через единый helper | API/service test |
| Alembic baseline | schema creation по-прежнему проходит | existing migration tests |
| Warnings budget | нет новых app-level warnings; known external warnings явно учтены | `make test` output |

**Acceptance checklist для PR итерации 4:**

- [ ] `asyncio_default_fixture_loop_scope` задан явно.
- [ ] В `backend/app` нет прямых вызовов `datetime.utcnow()`.
- [ ] Есть единый helper для UTC timestamps и он используется в models/services.
- [ ] API timestamp responses не сломаны.
- [ ] Миграции не требуют изменения, либо изменение осознанно оформлено Alembic revision.
- [ ] Warning budget зафиксирован без широкого подавления всех warnings.
- [ ] В PR/testing notes указано количество warnings до/после.

**Команды проверки перед завершением итерации:**

```bash
rg -n "datetime\.utcnow|utcnow" backend/app backend/tests
make compileall
make test
```

Если меняется только документация планирования, достаточно `git diff --check`; при реализации timestamp/config изменений обязательны `make compileall` и `make test`.

### 9.6 Рекомендуемый порядок выполнения

| Порядок | Работа | Почему именно сейчас | Основной результат |
|---:|---|---|---|
| 1 | Readiness и TeX diagnostics | Без этого непонятно, какие возможности реально доступны в окружении | `/api/ready`, tests, README notes |
| 2 | Artifact hardening | Compile/export — самый рискованный filesystem boundary | Общий safe download/cleanup механизм |
| 3 | Frontend regression baseline | Нужно защитить текущий UI перед дальнейшими изменениями | Script-order test и первый browser smoke |
| 4 | Warnings cleanup | Снижает шум и повышает доверие к тестам | Меньше warnings, timezone-aware timestamps |
| 5 | Async jobs design spike | После стабилизации runtime можно проектировать job API | ADR/mini design для compile jobs |

### 9.7 Что не делать в ближайшем спринте

Чтобы не размывать фокус, в ближайший спринт **не включать**:

- полноценную auth/multi-user модель;
- большой переход frontend на bundler/framework;
- масштабную переработку AI prompt UX;
- перенос всех тяжёлых операций на Celery без предварительного design spike;
- новые крупные шаблоны/редакционные возможности, не связанные со стабилизацией runtime.

Эти задачи важны, но они должны идти после readiness, artifact safety и базового E2E smoke.

## 10. План встраивания фичи «занятие → запись → транскрипт → AI-документы ученика»

### 10.1 Цель и продуктовый сценарий

Новая фича расширяет Latexed от редактора/генератора LaTeX до учебного workflow для преподавателя:

1. преподаватель выбирает ученика из своего списка и начинает занятие по конкретной теме;
2. по явной опции сервис записывает звук занятия;
3. backend передаёт запись в transcription pipeline; черновой скрипт `transcribe.py` должен быть адаптирован в service layer;
4. AI pipeline обрабатывает транскрипт по промптам `check_list.txt` и `pupil_mistakes.txt`;
5. backend генерирует PDF-документы: чек-лист и ревью ошибок, названные по теме занятия;
6. документы сохраняются в папку ученика внутри директории соответствующей даты и доступны для просмотра/скачивания.

Целевая ценность: после урока преподаватель получает структурированные материалы без ручного переписывания аудио и без ручной сборки LaTeX/PDF.

### 10.2 Важное наблюдение по текущему репозиторию

На момент анализа команды поиска по репозиторию не нашли `transcribe.py`, `check_list.txt` и `pupil_mistakes.txt` в текущем checkout. Поэтому план закладывает два параллельных результата:

- интеграционный контракт и места подключения этих артефактов;
- безопасный fallback/заглушки для тестов, чтобы backend-домен можно было разработать до появления production-скрипта и финальных prompt-файлов.

Когда файлы будут добавлены, их следует разместить в предсказуемых директориях:

```text
backend/app/services/transcription.py       # адаптер вокруг transcribe.py
backend/app/prompts/lesson/check_list.txt
backend/app/prompts/lesson/pupil_mistakes.txt
```

Если `transcribe.py` должен остаться standalone-скриптом, backend всё равно должен обращаться к нему через service adapter, а не вызывать из router напрямую.

### 10.3 Архитектурные принципы встраивания

Фичу следует встраивать в текущую архитектуру Latexed без смешивания HTTP, storage, AI и PDF-логики:

```text
Router layer
  → lesson/pupil schemas
  → LessonService / PupilService
  → AudioStorageService / TranscriptionService
  → LessonDocumentGenerationService
  → existing AI generation and LaTeX/PDF services
  → SQLAlchemy models + runtime artifact directories
```

Ключевые правила:

- routers отвечают только за HTTP-контракты, upload/download, status codes и dependency wiring;
- services отвечают за выбор директорий, валидацию имён, запуск transcription/AI/PDF workflows и транзакции;
- models хранят состояние, но не запускают subprocess, AI calls или файловые операции;
- все download paths должны использовать уже введённый safe artifact mechanism, а не ручную сборку путей;
- prompt text, transcript и аудио не должны попадать в логи целиком;
- запись аудио запускается только явным действием пользователя и должна иметь понятный consent/status UX.

### 10.4 Доменная модель данных

Минимальный набор сущностей для первой production-ready версии:

| Entity | Назначение | Основные поля |
|---|---|---|
| `Pupil` | Ученик преподавателя | `id`, `teacher_id`, `display_name`, `notes`, `created_at`, `updated_at` |
| `Lesson` | Конкретное занятие с учеником | `id`, `pupil_id`, `teacher_id`, `topic`, `lesson_date`, `status`, `created_at`, `updated_at` |
| `LessonAudioRecording` | Метаданные аудиозаписи | `id`, `lesson_id`, `filename`, `content_type`, `size_bytes`, `duration_seconds`, `storage_path`, `status` |
| `LessonTranscript` | Результат транскрибации | `id`, `lesson_id`, `recording_id`, `provider`, `language`, `text`, `status`, `error_message`, `created_at` |
| `LessonGeneratedDocument` | Чек-лист / ревью ошибок / будущие документы | `id`, `lesson_id`, `document_type`, `title`, `filename`, `storage_path`, `status`, `error_message`, `created_at` |
| `LessonProcessingJob` | Асинхронное состояние pipeline | `id`, `lesson_id`, `job_type`, `status`, `started_at`, `finished_at`, `error_message` |

На первом этапе можно использовать `teacher_id` как строковый внешний идентификатор или placeholder, потому что полноценная auth/multi-user модель ещё не внедрена. При последующей auth-итерации это поле связывается с реальным пользователем.

Рекомендуемые статусы:

```text
Lesson.status:
  draft → recording_uploaded → transcribing → transcript_ready → generating_documents → completed
                                                ↘ failed

LessonAudioRecording.status:
  uploaded → accepted → rejected

LessonTranscript.status:
  pending → running → ready | failed

LessonGeneratedDocument.status:
  pending → generating → ready | failed
```

### 10.5 Storage layout для аудио, транскриптов и документов

Все runtime-файлы уроков должны находиться внутри отдельного trusted root, например `${UPLOAD_DIR}/lessons` или `${ARTIFACT_ROOT}/lessons`.

Рекомендуемая структура:

```text
runtime/lessons/
  teacher_<teacher_id>/
    pupil_<pupil_id>/
      2026-06-09/
        lesson_<lesson_id>/
          audio/
            recording.webm
          transcripts/
            transcript.txt
            transcript.json
          documents/
            tema-zanyatiya-check-list.pdf
            tema-zanyatiya-pupil-mistakes.pdf
            tema-zanyatiya-check-list.tex
            tema-zanyatiya-pupil-mistakes.tex
```

Правила безопасности:

- пользовательские `topic`, имена учеников и исходные имена файлов нельзя напрямую использовать как paths;
- все части путей должны проходить slug/safe filename helper;
- download endpoints должны отдавать только документы, связанные с `LessonGeneratedDocument`, а не любой файл по имени;
- cleanup должен принимать только trusted lesson root и не удалять файлы вне runtime directories;
- для аудио следует ограничить `content_type`, размер и длительность.

### 10.6 API-контракты

#### Pupil API

```text
GET    /api/pupils
POST   /api/pupils
GET    /api/pupils/{pupil_id}
PATCH  /api/pupils/{pupil_id}
DELETE /api/pupils/{pupil_id}
```

Минимальные schemas:

```text
PupilCreate: display_name, notes?
PupilUpdate: display_name?, notes?
PupilResponse: id, teacher_id, display_name, notes, created_at, updated_at
```

#### Lesson API

```text
POST   /api/lessons
GET    /api/lessons?pupil_id=&date_from=&date_to=
GET    /api/lessons/{lesson_id}
PATCH  /api/lessons/{lesson_id}
DELETE /api/lessons/{lesson_id}
```

Минимальные schemas:

```text
LessonCreate: pupil_id, topic, lesson_date?
LessonUpdate: topic?, lesson_date?, status?
LessonResponse: id, pupil_id, teacher_id, topic, lesson_date, status, documents[], transcript?
```

#### Audio upload / transcription / document generation API

```text
POST /api/lessons/{lesson_id}/recordings
POST /api/lessons/{lesson_id}/transcribe
POST /api/lessons/{lesson_id}/documents/generate
GET  /api/lessons/{lesson_id}/documents
GET  /api/lessons/{lesson_id}/documents/{document_id}/download
GET  /api/lessons/{lesson_id}/processing-status
```

Переходный синхронный вариант допустим только для MVP и тестов. Production-направление — job-based pipeline:

```text
POST /api/lessons/{lesson_id}/processing-jobs
GET  /api/lessons/{lesson_id}/processing-jobs/{job_id}
```

### 10.7 Transcription pipeline

`transcribe.py` нужно превратить в адаптер с явным контрактом:

```text
TranscriptionService.transcribe(recording_path, language="ru") -> TranscriptResult

TranscriptResult:
  text: str
  language: str
  provider: str
  duration_seconds?: float
  confidence?: float
  segments?: list
```

Порядок реализации:

1. перенести reusable-часть `transcribe.py` в `backend/app/services/transcription.py`;
2. оставить CLI wrapper, если скрипт нужен для ручного запуска;
3. добавить настройки provider/model/API keys через `backend/app/config.py`;
4. добавить size/duration/content-type validation до запуска транскрибации;
5. сохранять raw transcript и normalized transcript отдельно;
6. тестировать service через fake transcription provider, чтобы CI не зависел от внешней нейросети.

Failure behavior:

- если provider недоступен, lesson остаётся в статусе `recording_uploaded`, transcript получает `failed`;
- повторный запуск transcription разрешён, но должен создавать новую попытку или обновлять статус явно;
- текст ошибки в API должен быть кратким и не содержать ключи/provider payload.

### 10.8 AI processing pipeline для чек-листа и ревью ошибок

Промпты `check_list.txt` и `pupil_mistakes.txt` нужно подключить через отдельный prompt loader:

```text
LessonPromptService.load("check_list")
LessonPromptService.load("pupil_mistakes")
LessonDocumentGenerationService.generate_documents(lesson_id)
```

Входные данные prompt-а:

- тема занятия;
- дата занятия;
- имя/идентификатор ученика;
- transcript text;
- optional teacher notes;
- формат результата: структурированный JSON или строго ограниченный LaTeX fragment.

Рекомендуемый формат AI output: structured JSON, из которого backend строит LaTeX сам. Это безопаснее, чем разрешать модели возвращать полный `.tex` без контроля.

Пример целевого результата:

```text
check_list:
  title
  objectives[]
  completed[]
  homework[]
  next_steps[]

pupil_mistakes:
  title
  mistakes[]:
    topic
    quote_or_context
    explanation
    correction
    practice_task
```

Далее backend:

1. валидирует JSON schema;
2. экранирует LaTeX-special characters;
3. строит `.tex` через отдельный lesson document builder;
4. компилирует PDF через существующий `pdf_generator`/`latex_compiler` boundary;
5. сохраняет `LessonGeneratedDocument` metadata и безопасные filenames.

### 10.9 Frontend UX

Фронтенд-расширение лучше делать после backend foundation, не ломая существующий ordered script contract.

Новые UI-блоки:

- список учеников преподавателя;
- карточка ученика с историей занятий;
- форма создания занятия: тема, дата, заметки;
- блок записи аудио с состояниями `idle`, `recording`, `stopped`, `uploading`, `uploaded`, `transcribing`, `generating`, `completed`, `failed`;
- вкладка transcript preview;
- список generated documents с download buttons.

Технический подход:

- использовать браузерный `MediaRecorder`;
- хранить запись как `audio/webm` или другой поддерживаемый формат;
- добавить новый ordered script, например `frontend/js/10-lessons.js`;
- обновить `frontend/main.html` и contract test на порядок scripts;
- не вводить bundler/framework на этой итерации;
- если backend недоступен, UI должен показать degraded state и не терять уже введённые тему/заметки.

### 10.10 Итерационный roadmap внедрения

#### Итерация A. Backend domain foundation, 2–3 дня, P0

Цель: создать доменную основу без записи аудио и внешних AI calls.

Задачи:

- добавить SQLAlchemy models и Alembic migration для `Pupil`, `Lesson`, `LessonGeneratedDocument` минимум;
- добавить Pydantic schemas для pupil/lesson/document responses;
- добавить `PupilService` и `LessonService`;
- добавить routers `/api/pupils` и `/api/lessons`;
- добавить tests на CRUD, фильтрацию lessons по pupil/date и ownership placeholder;
- обновить README/API docs.

Definition of Done:

- можно создать ученика, создать занятие с темой, получить список занятий ученика;
- миграция соответствует models;
- `make compileall` и `make test` проходят.

#### Итерация B. Audio upload и безопасное lesson storage, 2–3 дня, P0

Цель: принимать аудио и сохранять его в trusted runtime root.

Задачи:

- добавить `LessonAudioRecording` model/migration;
- добавить `AudioStorageService` с safe path policy;
- добавить endpoint `POST /api/lessons/{lesson_id}/recordings`;
- ограничить content-type, размер, расширение и filename;
- добавить cleanup policy для lesson artifacts;
- добавить tests на path traversal, unsupported media type, oversized upload, сохранение валидного файла.

Definition of Done:

- запись аудио сохраняется только внутри trusted lesson root;
- API возвращает recording metadata;
- unsafe filename/content-type не проходят.

#### Итерация C. Transcription integration, 2–4 дня, P0/P1

Цель: подключить `transcribe.py` через service adapter.

Задачи:

- добавить `TranscriptionService` и fake provider для тестов;
- адаптировать `transcribe.py` к reusable function/API;
- добавить `LessonTranscript` model/migration;
- добавить endpoint `POST /api/lessons/{lesson_id}/transcribe`;
- сохранять transcript text и provider metadata;
- добавить tests на успешную транскрибацию и provider failure.

Definition of Done:

- по загруженной записи можно получить transcript record;
- failure provider-а не ломает lesson и отражается статусом `failed`;
- CI tests не требуют реального внешнего AI/transcription provider.

#### Итерация D. AI documents generation, 3–5 дней, P0/P1

Цель: генерировать чек-лист и ревью ошибок из transcript-а.

Задачи:

- добавить prompt files `check_list.txt`, `pupil_mistakes.txt` в `backend/app/prompts/lesson/`;
- добавить prompt loader и structured output contract;
- добавить `LessonDocumentGenerationService`;
- добавить LaTeX builder для lesson documents;
- использовать safe artifact paths и compile/export hardening;
- добавить endpoint `POST /api/lessons/{lesson_id}/documents/generate`;
- добавить download endpoint для generated documents;
- добавить tests на prompt loading, AI fake response, LaTeX escaping, PDF/document metadata persistence.

Definition of Done:

- из transcript-а создаются минимум два документа: чек-лист и ревью ошибок;
- filenames соответствуют теме занятия через slug, но не содержат unsafe path chars;
- download доступен только для documents, связанных с lesson.

#### Итерация E. Job-based orchestration, 3–5 дней, P1

Цель: не держать HTTP request во время транскрибации, AI и PDF compilation.

Задачи:

- добавить `LessonProcessingJob` model/migration;
- реализовать job statuses и polling endpoint;
- вынести transcription/generation pipeline в worker-friendly service;
- добавить retry/cancel policy;
- добавить tests на переходы статусов.

Definition of Done:

- frontend может запустить processing job и опрашивать статус;
- повторный запуск не создаёт неконтролируемые дубль-документы;
- ошибка одного этапа видна пользователю и не скрывает предыдущие результаты.

#### Итерация F. Frontend lesson workflow, 4–6 дней, P1

Цель: дать преподавателю UI для полного сценария.

Задачи:

- добавить UI списка учеников и занятий;
- добавить создание занятия и выбор темы;
- добавить MediaRecorder flow;
- добавить upload/progress/status UI;
- добавить transcript preview;
- добавить список и скачивание documents;
- добавить frontend contract test для нового script order;
- добавить E2E smoke: создать ученика → создать занятие → загрузить fake audio → увидеть статус и documents fallback.

Definition of Done:

- преподаватель проходит сценарий от выбора ученика до скачивания generated documents;
- graceful fallback работает при недоступном backend/provider;
- `make frontend-check`, `make test` и frontend smoke проходят или limitation явно описана.

### 10.11 Тестовая стратегия

| Уровень | Что покрыть | Инструмент |
|---|---|---|
| Unit/service | safe storage, slug filenames, prompt loading, transcription adapter, document builder | pytest |
| API/TestClient | pupils/lessons CRUD, audio upload, transcribe, generate, download | pytest + TestClient |
| Security regression | path traversal, absolute paths, unsupported extensions, symlink escape, oversized audio | pytest |
| AI/provider | fake transcription provider, fake generation provider, provider failure | pytest monkeypatch/fakes |
| Frontend contract | порядок scripts, наличие `10-lessons.js`, отсутствие legacy entrypoint | pytest static checks |
| E2E smoke | создать lesson workflow и проверить graceful statuses | Playwright или аналог |

Минимальный набор acceptance tests для первого релиза фичи:

- `test_create_pupil_and_lesson`;
- `test_audio_upload_rejects_path_traversal_filename`;
- `test_audio_upload_rejects_unsupported_content_type`;
- `test_transcription_success_with_fake_provider`;
- `test_document_generation_creates_checklist_and_mistakes_documents`;
- `test_lesson_document_download_rejects_cross_lesson_access`;
- `test_lesson_artifact_cleanup_does_not_escape_runtime_root`.

### 10.12 Observability и operational readiness

Readiness endpoint нужно расширять постепенно, не смешивая с liveness:

- `health` остаётся проверкой, что процесс отвечает HTTP;
- `ready` дополнительно может показывать:
  - доступность lesson artifact root на запись;
  - наличие transcription provider credentials/config;
  - доступность AI provider-а для lesson document generation;
  - доступность `pdflatex` для PDF-документов.

Логи и метрики:

- логировать `lesson_id`, `pupil_id`, `job_id`, stage, status, duration;
- не логировать полный transcript, audio path с персональными данными, prompt целиком или generated document text;
- собирать duration по этапам: upload, transcription, AI generation, PDF compile;
- фиксировать количество failed/retried jobs.

### 10.13 Основные риски и решения

| Риск | Почему важно | Митигация |
|---|---|---|
| Персональные данные в аудио/транскриптах | Высокая чувствительность данных учеников | consent UX, ограничение логов, lifecycle/cleanup, access control roadmap |
| Долгие AI/transcription операции | HTTP timeout и плохой UX | job pipeline и polling |
| Path traversal в именах тем/файлов | Риск чтения/записи вне runtime root | slug helper, trusted roots, download by DB id |
| Галлюцинации AI в документах | Неверные рекомендации ученику | structured output, validation, teacher review before final download |
| Отсутствие `pdflatex` | PDF generation может быть degraded | readiness, fallback `.tex`/HTML, docs по `make latex-check` |
| Нет auth модели | Нельзя безопасно разделять преподавателей | временный `teacher_id`, затем auth/ownership iteration |

### 10.14 Рекомендуемый первый PR

Первый PR должен быть узким и не должен одновременно включать запись аудио, transcription provider и frontend UI.

Рекомендуемый scope:

- models/migration/schemas/services/routers для `Pupil` и `Lesson`;
- базовые endpoints CRUD;
- tests на создание ученика, создание занятия, получение списка занятий ученика;
- README секция с описанием будущего lesson workflow и текущего backend foundation;
- без изменений в frontend и без внешних AI calls.

Такой scope снижает риск, даёт основу для хранения документов и позволит следующими PR подключать audio storage, transcription и generation по одному безопасному boundary за раз.
