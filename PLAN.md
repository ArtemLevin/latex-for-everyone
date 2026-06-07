# План дальнейшей разработки Latexed

## 1. Краткий анализ текущего состояния

Latexed уже имеет рабочий вертикальный срез онлайн LaTeX-редактора:

- **Backend:** FastAPI-приложение в `backend/app/` с роутерами проектов, файлов, компиляции, экспорта, шаблонов и AI-генерации.
- **Frontend:** single-page UI в `frontend/main.html` и модульные browser scripts в `frontend/js/`, где реализованы редактор, file tree, preview, export, AI-модалка и настройки.
- **Persistence:** SQLAlchemy-модели `Project`, `File`, `CompileHistory`, `ProjectSnapshot`; SQLite используется по умолчанию, Alembic scaffold присутствует.
- **LaTeX pipeline:** серверная компиляция через `pdflatex`, sanitizer известных AI/LaTeX ошибок, download endpoints для PDF/export artifacts.
- **AI pipeline:** prompt builder, provider/model status, Ollama/OpenAI-compatible вызовы, extraction LaTeX-кода, структурная validation, frontend insertion modes.
- **Quality baseline:** есть `pytest` API/service tests, `make compileall`, `make frontend-check`, `make check`, Docker backend path и документация для агентской работы.

Главный вывод: проект уже пригоден для локальной разработки и демонстрации, но до устойчивого production-ready редактора нужны системные улучшения в архитектуре, тестовой матрице, управлении артефактами, frontend надежности, безопасности и операционной документации.

## 2. Основные пробелы и риски

### 2.1 Архитектура backend

- Роутеры всё ещё часто напрямую используют SQLAlchemy `Session`; это допустимо как legacy/current style, но усложняет тестирование и повторное использование бизнес-логики.
- Нет выделенных сервисов для проектов/файлов/снапшотов/export orchestration; compile и AI уже лучше отделены.
- Автосоздание таблиц теперь должно быть локальной/dev-опцией (`AUTO_CREATE_TABLES`), а production-развёртывания должны опираться на Alembic migrations.

### 2.2 Данные и артефакты

- Локальные runtime SQLite файлы (`latexed.db`, `test_latexed.db`, `*.sqlite`) не должны попадать в git; это нужно регулярно контролировать через `.gitignore` и `git ls-files`.
- Generated PDF/export artifacts живут в локальных runtime директориях; нужна явная политика TTL, cleanup и storage abstraction для production.
- История AI-генераций отсутствует как persisted entity, поэтому воспроизводимость генераций ограничена.

### 2.3 LaTeX/security hardening

- Есть sanitizer и validator, но compile/export остаются высокорисковыми границами из-за subprocess и пользовательского `.tex`.
- Нужны более строгие ограничения на путь, размер проекта, число файлов, расширения, compile artifact TTL, stdout/stderr/log size.
- Нужна отдельная политика sandboxing: текущий `pdflatex` не должен получать доступ к произвольной файловой системе или shell escape.

### 2.4 Frontend надежность

- Frontend построен как набор global scripts без build step; это просто, но усложняет масштабирование и автоматическое тестирование UI flows.
- Нет browser E2E тестов для критичных сценариев: создать проект, редактировать файл, скомпилировать, экспортировать, выполнить AI generation.
- Offline/local fallback есть, но его поведение нужно формализовать и покрыть тестами.

### 2.5 Observability и эксплуатация

- Есть request logging и request IDs, но не хватает health/readiness детализации по DB, compiler, storage, AI provider.
- Нет документированного production checklist: env vars, secrets, CORS/hosts, storage cleanup, reverse proxy, backups, migrations.
- Celery/Redis scaffolding присутствует, но compile/export/generation пока в основном synchronous API flows.

## 3. Целевое направление

Цель развития: превратить Latexed из локального full-stack прототипа в устойчивый сервис для создания, AI-генерации, компиляции и экспорта LaTeX-документов.

Целевые принципы:

1. **Безопасные границы:** всё, что пересекает subprocess/provider/filesystem boundary, валидируется, лимитируется и логируется без утечки пользовательского контента.
2. **Стабильные API contracts:** схемы и frontend payloads меняются осознанно, с тестами и документацией.
3. **Инкрементальная архитектура:** новые сложные flows идут через services; legacy direct-DB routers рефакторятся постепенно.
4. **Воспроизводимость:** compile/export/AI actions имеют историю, метаданные, диагностируемые ошибки и cleanup policy.
5. **Проверяемость:** backend tests + frontend syntax checks + E2E для ключевых browser сценариев.

## 4. Roadmap по этапам

### Этап 1 — Репозиторная гигиена и baseline качества

**Приоритет:** P0

**Статус:** начат: runtime SQLite artifacts убраны из git tracking, правила ignore и cleanup задокументированы.

**Цель:** убрать источники нестабильности и зафиксировать минимальный quality gate.

**Работы:**

- Поддерживать отсутствие runtime DB artifacts (`latexed.db`, `test_latexed.db`, `*.sqlite`) в git и актуальные правила в `.gitignore`.
- Проверить, что tests сами создают/удаляют test DB и не зависят от tracked `.db` файлов.
- Добавить/уточнить README-раздел про локальные runtime artifacts и cleanup.
- Рассмотреть Makefile targets `lint` и `typecheck` или явно оставить только существующие checks в документации.
- В CI/локальном workflow закрепить минимум:
  - `make compileall`;
  - `make frontend-check`;
  - `make test`.

**Критерий готовности:** чистый checkout не содержит mutable runtime DB в tracked files; базовые проверки документированы и воспроизводимы.

### Этап 2 — Persistence и миграции

**Приоритет:** P0
**Статус:** реализован базовый вариант: добавлена initial Alembic revision и настройка `AUTO_CREATE_TABLES` для разделения local/dev startup и production migrations.

**Цель:** разделить локальное автосоздание таблиц и production migrations.

**Работы:**

- Принято решение: оставить автосоздание таблиц только как local/dev fallback под `AUTO_CREATE_TABLES=true`; для production — `AUTO_CREATE_TABLES=false` и явный `make migrate`.
- Добавлена первая Alembic revision для текущей схемы.
- Документирован migration workflow: `make migration`, review, `make migrate`.
- Проверить PostgreSQL compatibility для JSON/timestamps/string UUID fields.

**Критерий готовности:** схема БД воспроизводится миграциями, а startup behavior не конфликтует с production deployment.

### Этап 3 — Backend service layer для проектов и файлов

**Приоритет:** P1
**Статус:** начат: CRUD/snapshot/duplicate логика проектов и CRUD/upload логика файлов вынесены в `ProjectService` и `FileService`, роутеры оставлены HTTP-адаптерами.

**Цель:** уменьшить direct business logic в routers и упростить тестирование.

**Работы:**

- Выделен `ProjectService` для create/update/delete/duplicate/snapshot/restore flows.
- Выделен `FileService` для create/update/delete/upload-all и main-file invariants.
- Публичные endpoints и response schemas сохранены без breaking changes.
- Добавить service-level unit tests там, где логика станет не завязана на HTTP.
- Оставить SQLAlchemy session wiring в dependency layer/router, не вводя большой repository layer без необходимости.

**Критерий готовности:** новые и изменённые project/file flows проходят через services; routers стали тоньше, API поведение не изменилось.

### Этап 4 — Compile/export hardening

**Приоритет:** P0

**Статус:** начат: добавлены конфигурируемые лимиты количества файлов и размеров LaTeX payload для compile/export endpoints.

**Цель:** сделать LaTeX subprocess boundary безопаснее и диагностируемее.

**Работы:**

- Поддерживать и расширять явные лимиты:
  - максимальное количество файлов в compile/export request;
  - максимальный размер одного файла и всего project payload;
  - максимальный размер compiler log/output в API response;
  - TTL generated artifacts.
- Усилить filename allowlist: расширения `.tex`, `.bib`, изображения только из разрешённого списка при необходимости.
- Проверить, что `pdflatex` запускается без shell escape и не получает произвольные пути.
- Добавить регулярный cleanup для compile/export artifacts: Makefile target или scheduled task.
- Расширить tests на path traversal, oversized payloads, unsupported filenames/extensions, timeout и compiler error mapping.

**Критерий готовности:** compile/export flows имеют лимиты, безопасные ошибки и покрытие основных abuse cases.

### Этап 5 — AI generation v2

**Приоритет:** P1
**Статус:** начат: generation уже использует body-only contract, фиксированную преамбулу, language/source-mode поля, compile-check/auto-repair, pre-compile body sanitizer и validator баланса окружений/math delimiters перед возвратом результата.

**Цель:** сделать AI generation воспроизводимой, управляемой и удобной.

**Работы:**

- Добавить persisted `generation_history`:
  - `project_id`, provider, model, prompt hash, prompt preview, raw output/latex code policy, validation result, status, timestamps.
- Добавить endpoints:
  - `GET /api/generation/history/project/{project_id}`;
  - `GET /api/generation/history/item/{history_id}`;
  - при необходимости `POST /api/generation/history/{history_id}/restore`.
- Добавить `generate-to-project` endpoint для атомарной записи generated LaTeX в файл проекта на backend.
- Вынести provider/model presets в backend endpoint/config, чтобы frontend не был source of truth.
- Вынести prompt templates в конфигурационные файлы или отдельный модуль с тестируемыми template parts.
- Продолжить AI repair flow: первая автоматическая compile-check/repair итерация добавлена; дальше нужен UI для ошибок, повторов и ручного repair по compile/validation errors.

**Критерий готовности:** AI generation можно воспроизвести, открыть из истории, восстановить в проект и конфигурировать без правки frontend hardcode.

### Этап 6 — Frontend UX и тестируемость

**Приоритет:** P1

**Цель:** стабилизировать пользовательские browser flows.

**Работы:**

- Добавить Playwright или аналогичный E2E runner.
- Покрыть сценарии:
  - bootstrap при доступном backend;
  - offline/local fallback;
  - создание/переименование/удаление файла;
  - compile success/error UI;
  - export PDF/HTML/TEX UI;
  - AI prompt preview/provider status/generate/insert modes.
- Добавить Makefile target `frontend-e2e` и документацию по запуску.
- Зафиксировать DOM/test IDs для критичных элементов.
- Сохранить выбранные AI/UI настройки в `localStorage`, где это улучшает UX.

**Критерий готовности:** ключевые browser сценарии проверяются автоматизированно, а frontend изменения перестают быть только ручной проверкой.

### Этап 7 — Observability и operational readiness

**Приоритет:** P1

**Цель:** подготовить сервис к эксплуатации и диагностике.

**Работы:**

- Добавить readiness endpoint или расширенный health report для:
  - DB connectivity;
  - compiler availability;
  - writable compile/export directories;
  - AI provider optional status.
- Стандартизировать error codes/messages для compile/export/AI.
- Добавить structured logging для service boundaries с request_id.
- Документировать production env vars:
  - `DATABASE_URL`;
  - `SECRET_KEY`;
  - `CORS_ORIGINS`/`ALLOWED_HOSTS`;
  - `LATEX_COMPILER`/work dirs;
  - AI provider settings.
- Добавить deployment checklist и troubleshooting в README/docs.

**Критерий готовности:** оператор может понять состояние сервиса и диагностировать типовые сбои без чтения кода.

### Этап 8 — Async jobs для тяжёлых операций

**Приоритет:** P2

**Цель:** убрать долгие compile/export/AI operations из request-response path там, где это нужно.

**Работы:**

- Решить, какие операции остаются sync, а какие уходят в Celery/Redis.
- Сформировать job model/API:
  - create job;
  - get status;
  - get result/artifact;
  - cancel/retry.
- Использовать существующий `backend/app/worker.py` как стартовую точку или заменить на более явную job architecture.
- Обновить frontend на polling/websocket для job progress.

**Критерий готовности:** долгие операции не блокируют API worker и имеют понятный progress/result lifecycle.

### Этап 9 — Collaboration и project lifecycle

**Приоритет:** P2

**Цель:** улучшить работу с проектами без обязательного полноценного auth на первом шаге.

**Работы:**

- Ввести lightweight project access model: public/private links или owner token.
- Добавить project export/import bundle.
- Добавить versioned snapshots/diff view.
- Рассмотреть WebSocket live compile или collaborative presence только после стабилизации базового project lifecycle.

**Критерий готовности:** пользователь может безопаснее хранить, переносить и восстанавливать проекты.

## 5. Рекомендуемый порядок ближайших задач

1. **Repo hygiene:** убрать tracked `.db`, добавить `.gitignore`, проверить tests.
2. **Compile/export limits:** закрыть самые рискованные subprocess/filesystem abuse cases.
3. **Migration baseline:** создать/зафиксировать Alembic baseline и startup policy.
4. **Project/File services:** начать инкрементальный refactor с тестами без изменения API.
5. **AI history + generate-to-project:** сделать AI результат воспроизводимым и атомарно сохраняемым.
6. **Frontend E2E:** покрыть основные пользовательские сценарии.
7. **Readiness/ops docs:** подготовить production checklist и health diagnostics.

## 6. Definition of Done для этапов

Для каждого этапа:

- [ ] Изменения ограничены заявленным scope.
- [ ] Публичные API/schema изменения задокументированы.
- [ ] Добавлены или обновлены tests для нового поведения.
- [ ] Выполнены релевантные checks (`make compileall`, `make frontend-check`, `make test`, `make check`, `make latex-check` при необходимости).
- [ ] Environment limitations явно записаны, если проверка невозможна.
- [ ] Нет tracked runtime artifacts, secrets, generated PDFs или нерелевантного форматирования.
