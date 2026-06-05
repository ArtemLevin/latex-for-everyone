# AI Agent Workflow Guide

## Core Principle: Explore → Plan → Code → Verify

All complex tasks must follow this cycle. Never skip steps.


## Assumptions / Verify first

Before applying path-based examples, verify expected directories exist:

```bash
rg --files | head -n 50
for p in app tests alembic; do
  if [ -d "$p" ]; then
    echo "OK: $p/"
  else
    echo "MISSING: $p/ (treat path examples as pseudocode)"
  fi
done
```

If a directory is missing, treat path examples in this document as **pseudocode** and adapt commands to the actual repository structure.

---

## Phase 1: Explore

**Goal:** Understand context before making changes.

### When to Use Explore

- Starting a new feature
- Investigating a bug
- Before refactoring
- Understanding dependencies

### Explore Actions

```bash
# Verify repo file layout first
rg --files | head -n 50

# Find related code
rg -n "BookingService" -g "*.py"

# Read file structure
head -100 app/services/booking_service.py

# Check test coverage
pytest tests/ --cov=app --cov-report=term-missing
```

### Explore Output

Document findings:
- Location of relevant files
- Existing patterns to follow
- Dependencies and callers
- Similar implementations

---

## Phase 2: Plan

**Goal:** Create implementation blueprint before coding.

### When to Write a Plan

- Any feature with >3 files to modify
- Database schema changes
- API modifications
- Refactoring work

### Plan Template

```markdown
## Implementation Plan: [Feature Name]

### Components to Modify
1. `/app/api/endpoints/bookings.py` - Add new route
2. `/app/services/booking_service.py` - Add method
3. `/app/schemas/booking.py` - Add schema

### Dependencies
- Import BookingService in endpoint
- Add error handling for 404

### Testing Strategy
- Unit test for service method
- Integration test for endpoint
- Test error cases

### Risks
- Race condition in slot booking
- Mitigation: Database-level locking
```

### When NOT to Skip Planning

❌ Production code changes
❌ Database migrations
❌ Security-sensitive features
❌ Breaking API changes

---

## Phase 3: Code

**Goal:** Implement in small, verifiable increments.

### Coding Principles

1. **Small commits**: Each commit should be reviewable
2. **Tests first**: Write tests before or alongside code
3. **Type annotations**: Always include type hints
4. **Follow patterns**: Match existing code style

### Vibe Coding vs Analytical Work

**Vibe Coding OK for:**
- Prototypes and experiments
- Utility functions
- One-off scripts
- Easy-to-regenerate code

**Analytical Approach REQUIRED for:**
- Production business logic
- Database operations
- Authentication/authorization
- Payment processing
- Data migrations
- Cross-file changes

### Code Incrementally

```python
# ✅ Good: Small, testable function
async def check_availability(slot_start: datetime) -> bool:
    """Check if time slot is available."""
    return await self.repository.is_slot_available(slot_start)

# ❌ Bad: Large function doing multiple things
async def process_booking(data):
    # 100 lines of validation, database access, notifications...
```

---

## Phase 4: Verify

**Goal:** Ensure changes work correctly and don't break existing functionality.

### Verification Checklist

```bash
# Run tests
make test

# Check types
make typecheck

# Run linter
make lint

# Manual testing (if applicable)
curl http://localhost:8000/api/bookings
```

### Verify After Each Change

- Tests pass
- Types are correct
- Linting passes
- No regressions

---

## Interview Pattern

Use when requirements are unclear.

### Ask Clarifying Questions

```
Before implementing, clarify:

1. What is the expected input format?
2. What are the error conditions?
3. Are there edge cases to consider?
4. What is the expected output?
5. Are there performance requirements?
```

### Example Dialogue

```
User: Add booking cancellation

Agent: Let me clarify the requirements:

1. Should cancelled slots become immediately available?
2. Is there a cancellation deadline (e.g., 24 hours before)?
3. Should we notify the booking owner?
4. What status should cancelled bookings have?
5. Should we track cancellation reason?
```

---

## Restart with Accumulated Knowledge

When stuck or after major discoveries:

### How to Restart

```markdown
## Context Summary

So far I've learned:
1. BookingService handles all booking logic
2. Repository pattern is used for data access
3. Tests are in /tests/ following AAA pattern
4. Pydantic schemas validate all input

Current task: Add booking cancellation

Next step: Implement cancel_booking method in BookingService
```

---

## Critic Mode

Review your own work before submitting.

### Self-Review Questions

1. Does this follow project architecture?
2. Are all edge cases handled?
3. Are types complete?
4. Would I approve this PR?
5. What could go wrong?

### Critic Template

```markdown
## Self-Review

### Strengths
- Follows layered architecture
- Comprehensive test coverage
- Proper error handling

### Concerns
1. Race condition possible under high load
   - Consider adding database lock
   
2. Missing audit log for cancellations
   - Add event emission for tracking

### Recommendation
Address concern 1 before merge. Concern 2 can be follow-up.
```

---

## When to Use Subagents

| Task | Agent |
|------|-------|
| Find code locations | `explorer` |
| Debug failing test | `debugger` |
| Review before merge | `reviewer` |
| Complex investigation | `explorer` + `debugger` |

---

## Common Mistakes to Avoid

1. **Skipping Explore**: Leads to wrong assumptions
2. **No Plan**: Results in scattered changes
3. **Large Commits**: Hard to review and revert
4. **No Verification**: Misses regressions
5. **Ignoring Types**: Causes runtime errors
6. **Copying Legacy Patterns**: Perpetuates bad practices

---

## Definition of Done for doc usage

- [ ] Explore → Plan → Code → Verify flow was followed and documented in the PR notes.
- [ ] Repository structure was verified before using path-based examples (`app/`, `tests/`, `alembic/`).
- [ ] Search/file discovery commands use `rg`-based patterns (no legacy recursive grep/find examples).
- [ ] Verification commands were run as applicable (`make test`, `make lint`, `make typecheck`) or limitations were documented.
- [ ] Path-specific snippets were adapted to real repository structure (or explicitly treated as pseudocode).
- [ ] Final PR summary includes risks, tests/checks, and any unresolved assumptions.
