# AI Agent Guidelines


## Quick start (5 шагов)

1. Проверьте структуру репозитория и наличие ключевых директорий (`app/`, `tests/`, `alembic/`).
2. Определите scope задачи и соответствующий слой архитектуры (Endpoint / Service / Repository / DB).
3. Выполните цикл `Explore → Plan → Code → Verify` небольшими инкрементами.
4. Прогоните обязательные проверки (`make test`, `make lint`, `make typecheck`).
5. Сверьте результат с `Definition of Done` перед PR/merge.

## Assumptions / Verify first

Перед использованием path-based примеров проверьте, что ожидаемая структура действительно существует:

```bash
rg --files | head -n 50
for p in app tests alembic; do
  if [ -d "$p" ]; then
    echo "OK: $p/"
  else
    echo "MISSING: $p/ (примеры ниже считаются pseudocode)"
  fi
done
```

Если директория отсутствует, воспринимайте пути в примерах как **pseudocode** и адаптируйте команды под фактическую структуру репозитория.

## Project Overview

Booking calendar service (Cal.com-like) where users publish available time slots and others book meetings.

**Key Constraints:**
- No authentication, no user accounts
- No external calendar integrations
- 30-minute booking slots
- Owner can view upcoming bookings

## Project Structure

```
/app
  /api          # FastAPI endpoints (presentation layer)
  /services     # Business logic (service layer)
  /db
    /models     # SQLAlchemy models
    /repositories # Data access (repository layer)
  /schemas      # Pydantic validation schemas
  /exceptions.py # Custom exceptions
/tests
  /api          # API integration tests
  /services     # Service unit tests
  /db           # Repository tests
/alembic        # Database migrations
```

## Commands

```bash
make setup       # Initial setup
make dev         # Run development server
make test        # Run all tests
make lint        # Run linter (ruff/flake8)
make typecheck   # Run type checker (mypy)
make migrate     # Run database migrations
make coverage    # Generate coverage report
```

## Architecture Rules

### Layered Architecture (STRICT)

```
Endpoint → Service → Repository → Database
```

**Prohibited:**
- ❌ Direct DB access from endpoints
- ❌ Business logic in endpoints
- ❌ HTTP requests from models
- ❌ Bypassing service layer
- ❌ Creating parallel types/entities

### SOLID Principles

- **Single Responsibility**: One class, one purpose
- **Open/Closed**: Extend without modifying
- **Liskov Substitution**: Subtypes must be substitutable
- **Interface Segregation**: Small, focused interfaces
- **Dependency Inversion**: Depend on abstractions

## Types and Data Models

### Type Annotations (REQUIRED)

```python
# ✅ Good
async def create_booking(
    slot_start: datetime,
    email: str
) -> Booking:
    ...

# ❌ Bad
async def create_booking(slot_start, email):
    ...
```

### Pydantic Validation

```python
from pydantic import BaseModel, EmailStr

class BookingCreate(BaseModel):
    slot_start: datetime
    customer_name: str = Field(min_length=2)
    customer_email: EmailStr
```

### Rules

1. Search existing types before creating new ones
2. Use `Enum`/`Union`/`Literal` for allowed values
3. Run `make typecheck` after changes
4. Avoid `Any` without justification

## Testing Rules

### Coverage Target

- **Minimum**: 80% for modified code
- **Required**: All public methods tested

### Test Structure (AAA Pattern)

```python
async def test_create_booking_success(self, booking_service):
    # Arrange
    slot_start = datetime(2025, 1, 15, 10, 0)
    
    # Act
    result = await booking_service.create_booking(...)
    
    # Assert
    assert result.slot_start == slot_start
```

### What to Test

- Happy path
- Edge cases
- Error conditions
- Boundary values

## Code Style

### Naming

- Classes: `PascalCase` (BookingService)
- Functions: `snake_case` (create_booking)
- Constants: `UPPER_CASE` (MAX_BOOKING_DAYS)
- Private: `_prefix` (_internal_method)

### Function Size

- Maximum ~50 lines
- Extract complex logic to separate functions

### Imports

```python
# Standard library
from datetime import datetime

# Third-party
from fastapi import APIRouter

# First-party
from app.services.booking_service import BookingService
```

## Comments

### Write "Why", Not "What"

```python
# ❌ Bad (restates code)
# Check if slot is available
if not available:
    raise Error()

# ✅ Good (explains reason)
# Prevent double-booking: race condition possible under high load
if not available:
    raise SlotNotAvailableError()
```

### Document

- Workarounds
- API limitations
- Business reasons
- Non-trivial decisions

## Legacy and Migrations

### Working with Legacy Code

1. Do not use legacy patterns as examples
2. Add tests before refactoring
3. Incremental improvements preferred
4. Document technical debt with TODO comments

### Migration Process

1. Plan migration in issue tracker
2. Write failing tests first
3. Implement minimal change
4. Verify all tests pass
5. Update documentation

## Agent Workflow

### Always Follow: Explore → Plan → Code → Verify

#### 1. Explore
- Read existing code
- Understand context
- Find similar patterns

#### 2. Plan
- Write implementation plan
- List components to modify
- Identify risks

#### 3. Code
- Small, incremental changes
- Commit frequently
- Keep tests passing

#### 4. Verify
- Run `make test`
- Run `make lint`
- Run `make typecheck`
- Manual testing if needed

### Vibe Coding vs Analytical Work

**Vibe Coding OK for:**
- Prototypes
- Utilities
- Parsers
- Easy-to-regenerate code

**Analytical Approach REQUIRED for:**
- Production code
- Refactoring
- Migrations
- Security-sensitive code
- Related changes across files

## Safety Rules

### Permissions

- ❌ Never delete files without confirmation
- ❌ Never run destructive commands (`rm -rf`, `DROP TABLE`)
- ❌ Never commit secrets
- ❌ Never modify files you don't understand

### MCP Servers

- Use only for stateful integrations (browser, DB)
- Minimal required permissions
- Prefer CLI when possible

### Data Protection

- Do not log sensitive data
- Do not expose PII in errors
- Validate all user input

## Quick Reference

| Task | Command |
|------|---------|
| Setup | `make setup` |
| Dev server | `make dev` |
| Tests | `make test` |
| Lint | `make lint` |
| Type check | `make typecheck` |
| Migrate | `make migrate` |
| Coverage | `make coverage` |

## Skills Available

- `new-endpoint` — Create API endpoints
- `add-tests` — Write comprehensive tests
- `code-review` — Review code changes
- `db-migration` — Database schema changes
- `debug-failing-test` — Diagnose test failures
- `refactor-module` — Improve code structure

## Subagents Available

- `explorer` — Read-only code investigation
- `debugger` — Bug diagnosis (no code changes)
- `reviewer` — Code review feedback

## Definition of Done (DoD)

- [ ] Изменения реализуют согласованный scope задачи и соответствуют архитектурному слою.
- [ ] Для нового/измененного поведения добавлены или обновлены тесты (happy path, edge, error/conflict; concurrency где применимо).
- [ ] Выполнены `make test`, `make lint`, `make typecheck`; падения устранены или явно задокументированы.
- [ ] Документация обновлена при изменении API, поведения или операционного процесса.
- [ ] Нет нарушений архитектуры `Endpoint → Service → Repository → Database`.
- [ ] Сохранена типизация и валидация входных/выходных контрактов.
- [ ] Финальный diff очищен от временного debug-кода и нерелевантных правок.
