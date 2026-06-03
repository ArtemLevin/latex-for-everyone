# План дальнейшей реализации AI-generation функционала

Текущий статус: базовая связка frontend ↔ backend уже реализована. Backend умеет строить prompt, проверять provider/model, вызывать Ollama или OpenAI-compatible vendor, извлекать LaTeX, выполнять структурную валидацию и отдавать результат. Frontend умеет открыть AI-форму, проверить provider, preview prompt, проверить `.tex`, сгенерировать документ, разместить код в выбранном target-файле, сохранить и запустить компиляцию.

## Этап 7 — UX и безопасная вставка результата

**Статус:** реализован в текущей итерации.

**Цель:** снизить риск случайной потери текущего `.tex` и сделать генерацию понятнее пользователю.

**Реализовано:**

- Добавлены режимы размещения результата: создать новый файл, заменить текущий файл, вставить в конец текущего файла.
- Добавлено подтверждение перед заменой активного файла.
- Добавлены loading states для кнопок prompt/provider/validation/generate.
- Добавлены кнопки копирования prompt и raw output.
- Validation errors/warnings выводятся списком.

**Что можно улучшить дополнительно:**

- Показать отдельный provider/model status badge в AI-модалке.
- Добавить сохранение выбранного режима вставки в `localStorage`.
- Добавить визуальный preview generated LaTeX до вставки в файл.

**Критерий готовности:** пользователь явно выбирает, что делать с generated LaTeX, и не может случайно перезаписать активный файл без подтверждения.

## Этап 8 — Безопасность, лимиты и hardening

**Статус:** реализован в текущей итерации.

**Цель:** подготовить AI endpoints к реальному использованию и защитить backend от больших/опасных payload-ов.

**Реализовано:**

- Добавлены конфигурируемые лимиты на размер `materials`, итогового prompt, raw output и payload для LaTeX validation.
- Добавлен отдельный timeout `AI_PROVIDER_STATUS_TIMEOUT` для быстрых проверок provider/model status.
- Добавлен in-memory rate limiting для generation endpoints с настройкой `AI_RATE_LIMIT_PER_MINUTE`.
- В production provider errors по умолчанию скрываются от пользователя; подробности можно включить через `DEBUG` или `AI_EXPOSE_PROVIDER_ERRORS`.
- LaTeX validator расширен запретами на потенциально опасные команды и пути:
  - `\write18`;
  - `\input|...`;
  - `\openout`;
  - абсолютные и родительские пути в `\input`/`\include`;
  - внешние/абсолютные пути в `\includegraphics`.
- Добавлены API-тесты на лимиты, rate limiting, sanitizing provider errors и validator-denylist.

**Что можно улучшить дополнительно:**

- Заменить in-memory limiter на Redis/DB-backed limiter для multi-process deployment.
- Делать лимиты user/project scoped после появления авторизации.
- Добавить audit-log по заблокированным generation запросам.
- Добавить отдельные лимиты для `/generate` и дешевых endpoint-ов (`/prompt`, `/validate`, `/providers/status`).

**Критерий готовности:** generation API устойчив к слишком большим запросам, опасным LaTeX-командам и повторным частым вызовам.

## Этап 9 — AI repair compile errors

**Цель:** дать пользователю возможность исправлять ошибки компиляции через AI.

**Работы:**

- Добавить endpoint `POST /api/generation/repair`.
- Payload:
  - `latex_code`;
  - `compile_error`;
  - `provider`;
  - `model`;
  - опционально `project_id`.
- Prompt repair должен требовать вернуть только исправленный LaTeX от `\documentclass` до `\end{document}`.
- Frontend-кнопка: `Исправить ошибку через AI` в error panel.
- После repair: validate → вставить/создать файл → compile.

**Критерий готовности:** если compile endpoint вернул ошибку, пользователь может запустить AI repair и получить исправленную версию документа.

## Этап 10 — История AI-генераций

**Цель:** обеспечить воспроизводимость и отладку AI-генераций.

**Работы:**

- Добавить модель/таблицу `generation_history`.
- Поля:
  - `id`;
  - `project_id`;
  - `provider`;
  - `model`;
  - `prompt_hash`;
  - `prompt_preview` или truncated prompt;
  - `raw_output`;
  - `latex_code`;
  - `validation`;
  - `status`;
  - `created_at`.
- Добавить endpoints:
  - `GET /api/generation/history/project/{project_id}`;
  - `GET /api/generation/history/item/{history_id}`.
- Frontend: вкладка истории AI-генераций.

**Критерий готовности:** прошлую генерацию можно найти, открыть, повторить или восстановить.

## Этап 11 — Generate-to-project endpoint

**Цель:** перенести атомарную запись generated LaTeX из frontend-логики в backend.

**Работы:**

- Добавить endpoint `POST /api/generation/generate-to-project`.
- Endpoint должен:
  - принять параметры генерации и `project_id`;
  - вызвать provider;
  - извлечь и провалидировать LaTeX;
  - создать новый файл или обновить существующий;
  - вернуть `FileResponse`, validation и generation metadata.
- Frontend должен использовать этот endpoint для режима `создать generated.tex` или `заменить текущий файл`.

**Критерий готовности:** generated LaTeX сохраняется в проект атомарно на backend, а frontend только обновляет локальное состояние из ответа API.

## Этап 12 — Provider/model presets

**Цель:** убрать hardcode provider/model из frontend.

**Работы:**

- Добавить endpoint `GET /api/generation/providers`.
- Возвращать доступные provider presets:
  - id;
  - name;
  - default model;
  - description;
  - required env vars.
- Frontend строит provider select из API, а не из hardcoded options.
- Опционально подтягивать список моделей Ollama из `/api/tags`.

**Критерий готовности:** frontend не содержит жестко зашитые provider/model presets.

## Этап 13 — Prompt-template management

**Цель:** сделать prompt и presets изменяемыми без правки Python-кода.

**Работы:**

- Вынести prompt templates в отдельный YAML/JSON/Markdown-файл или таблицу БД.
- Разделить:
  - role;
  - output contract;
  - correctness rules;
  - style rules;
  - subject presets;
  - difficulty presets.
- Добавить tests, что prompt builder корректно собирает итоговый prompt из template parts.
- Опционально добавить endpoint preview конкретного prompt template.

**Критерий готовности:** prompt можно менять как конфигурацию, не трогая backend service code.

## Этап 14 — Frontend E2E tests

**Цель:** автоматически проверять ключевые browser-flow сценарии.

**Работы:**

- Добавить Playwright или аналогичный browser-test runner.
- Сценарии:
  - открыть `frontend/main.html`;
  - замокать backend health/project/files/generation endpoints;
  - открыть AI-модалку;
  - заполнить тему;
  - нажать generate;
  - проверить вставку generated LaTeX в editor;
  - проверить validation/provider buttons.
- Добавить Makefile target `frontend-e2e`.

**Критерий готовности:** AI frontend flow проверяется не только static contract tests, но и реальным browser scenario.

## Этап 15 — Docker/compose with Ollama

**Цель:** упростить локальный запуск всего AI-контура.

**Работы:**

- Добавить docker-compose profile для Ollama или отдельные инструкции запуска Ollama рядом с backend.
- Документировать:
  - `ollama pull qwen2.5:14b`;
  - `OLLAMA_BASE_URL=http://ollama:11434` для backend внутри compose-сети.
- Добавить Makefile targets для docker AI workflow, например:
  - `docker-ai-up`;
  - `docker-ai-down`;
  - `docker-ai-logs`.
- Добавить README troubleshooting для compose/network/model pull.

**Критерий готовности:** разработчик может поднять backend + frontend + Ollama по документированному сценарию без ручной настройки URL-ов.
