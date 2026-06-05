# Prompting Guide for AI Agents

## Good vs Bad Prompts

### ❌ Bad: Vague Request

```
Add booking feature
```

**Problems:**
- No context about what "booking" means
- No specification of input/output
- No mention of existing patterns
- No constraints or requirements

### ✅ Good: Specific Request with Context

```
Add POST /api/bookings endpoint for creating bookings.

Requirements:
- Input: slot_start (datetime), customer_name, customer_email
- Output: BookingResponse with id and status
- Validate email format using Pydantic
- Check slot availability before creating
- Return 409 if slot already booked

Follow existing patterns in:
- /app/api/endpoints/bookings.py (existing GET endpoint)
- /app/services/booking_service.py

Include:
- Unit tests for service method
- Integration test for endpoint
- Error handling for invalid input
```

---

## Explore Phase Prompts

### Broad Exploration

```
Find all files related to booking functionality.
Show me:
1. Where BookingService is defined
2. All endpoints that use it
3. Test files for booking
4. Database models involved
```

### Pattern Discovery

```
Show me how existing endpoints handle:
1. Input validation
2. Error responses
3. Database transactions
4. Response serialization

I want to follow the same patterns.
```

### Dependency Analysis

```
What depends on BookingRepository?
List all imports and usages.
Are there any circular dependencies?
```

---

## Plan Phase Prompts

### Implementation Plan Request

```
Create implementation plan for adding booking cancellation.

Consider:
1. What files need modification
2. New methods required
3. Database changes (if any)
4. Test coverage needed
5. Potential risks

Output as markdown with sections.
```

### Risk Assessment

```
What are the risks of implementing concurrent booking prevention?

Consider:
- Race conditions
- Database locking
- Performance impact
- Edge cases
```

---

## Code Phase Prompts

### Specific Implementation

```
Implement cancel_booking method in BookingService.

Signature:
async def cancel_booking(self, booking_id: int, reason: str = None) -> Booking

Requirements:
- Update status to CANCELLED
- Store cancellation reason if provided
- Emit cancellation event
- Return updated booking

Follow existing patterns in create_booking method.
```

### Refactoring Request

```
Refactor validate_email method to be more robust.

Current issues:
- Doesn't check domain validity
- No MX record check (optional)
- Doesn't handle international domains

Keep backward compatibility.
Add unit tests for new cases.
```

---

## Review Prompts

### Self-Review Before Submitting

```
Review this implementation for:
1. Architecture compliance
2. Type safety
3. Error handling
4. Test coverage
5. Security concerns

Be critical. What would you reject in a PR?
```

### Impact Analysis

```
What code is affected by changing Booking.status from string to enum?

List:
1. Files that need updates
2. Tests that will fail
3. API responses that change
4. Database migration needed
```

---

## Debugging Prompts

### Test Failure Investigation

```
This test is failing:
[ paste error message ]

Test code:
[ paste test ]

Analyze:
1. What assertion failed
2. Expected vs actual values
3. Possible root causes
4. How to fix
```

### Production Bug Diagnosis

```
Users report: "Cannot book slots after 10 PM"

Error logs show:
[ paste logs ]

Investigate:
1. Timezone handling
2. Date comparison logic
3. Edge cases around midnight
```

---

## Interview Pattern Prompts

### Clarifying Requirements

```
Before I implement [feature], let me confirm:

1. What is the expected input format?
2. What are the error conditions?
3. Should this be async or sync?
4. Any performance requirements?
5. How should errors be handled?
6. Are there edge cases to consider?
```

### Confirming Understanding

```
Let me summarize my understanding:

- User books a 30-minute slot
- Slot must be in the future
- Email confirmation is sent
- Double-booking is prevented

Is this correct? What am I missing?
```

---

## Restart Prompts

### After Getting Stuck

```
Let me restart with what I've learned:

Known:
- BookingService is the entry point
- Repository handles DB access
- Pydantic validates input

Problem:
- Need to prevent race conditions

New approach:
- Use database-level locking
- Implement optimistic concurrency

Next step: Research SQLAlchemy locking options.
```

### Context Refresh

```
Summary of current state:

Files modified:
- app/services/booking_service.py (added cancel method)
- app/api/endpoints/bookings.py (added cancel route)

Tests:
- 3 unit tests passing
- 1 integration test failing

Issue:
- Transaction not rolling back on error

Next: Debug transaction handling.
```

---

## Critic Mode Prompts

### Pre-Submission Review

```
Act as a skeptical reviewer. Critique this code:

[ paste code ]

Questions to answer:
1. Would you approve this PR?
2. What edge cases are missing?
3. What could break in production?
4. Is testing sufficient?
5. Any security concerns?
```

### Architecture Review

```
Does this implementation follow our architecture?

Check:
- Layered architecture respected
- No direct DB access from endpoint
- Service layer contains business logic
- Proper error handling
- Type annotations complete
```

---

## Subagent Invocation Prompts

### When to Call Explorer

```
@explorer Find all usages of BookingRepository.get_by_id
I need to know what breaks if I change the return type.
```

### When to Call Debugger

```
@debugger This test fails intermittently:
[ paste test ]

Please diagnose without modifying code.
Provide reproduction steps and likely cause.
```

### When to Call Reviewer

```
@reviewer Please review this PR before merge:
[ paste diff ]

Focus on:
- Security implications
- Race condition potential
- Missing error handling
```

---

## Anti-Patterns to Avoid

### ❌ Don't Ask Agent to Guess

```
Bad: Just add authentication

Good: Add JWT-based authentication with:
- /auth/login endpoint
- Token expiration: 24 hours
- Refresh token support
- Store hashed passwords with bcrypt
```

### ❌ Don't Skip Verification

```
Bad: Here's the code, done!

Good: Code implemented. Verification:
- make test: 15 passed
- make lint: no issues
- make typecheck: clean
- Manual test: curl result attached
```

### ❌ Don't Ignore Errors

```
Bad: Tests failing but code works

Good: Tests failing due to timezone issue.
Root cause: datetime.utcnow() vs datetime.now(tz).
Fix applied and verified.
```

---

## Structured Prompt Templates

Use this structure for most non-trivial requests.

### Template

```markdown
## Context
- What feature/bug/task this is
- Current state and known constraints

## Constraints
- Architecture boundaries
- Performance/security requirements
- Tooling or repo limitations

## Acceptance Criteria
- Observable behaviors that must pass
- Required tests/checks
- Error cases that must be handled

## Non-goals
- What should NOT be changed in this task
- Explicit out-of-scope items

## Expected Output Format
- plan only / patch only / review only
- required sections in final response
- citations/commands/reporting requirements
```

### Example (filled)

```markdown
## Context
Add cancellation endpoint for bookings.
Current repo uses layered architecture with service and repository layers.

## Constraints
- Endpoint must not access DB directly.
- Keep existing response schema style.
- Do not introduce auth.

## Acceptance Criteria
- `POST /api/bookings/{id}/cancel` returns 200 on success.
- Returns 404 for missing booking.
- Unit + integration tests added.
- `make test`, `make lint`, `make typecheck` pass.

## Non-goals
- No calendar integrations.
- No notification delivery implementation.

## Expected Output Format
- First: implementation plan.
- Then: patch summary with changed files.
- Finally: test command results.
```

---

## Bad assumptions to avoid

- Assuming files/endpoints exist without checking repository paths first.
- Assuming legacy examples are production-ready instead of pseudocode/reference patterns.
- Assuming success path is enough (ignore validation, conflict, not-found, boundary cases).
- Assuming architecture exceptions are acceptable for "small" changes.
- Assuming tests are optional for docs-guided feature work.

---

## Prompt + expected artifact examples

### 1) Plan only

**Prompt**

```text
Create an implementation plan for adding booking cancellation.
Do not modify files yet.
Include risks, dependencies, and test strategy.
```

**Expected artifact**
- Markdown plan with sections: scope, files, risks, tests.
- No code patch.

### 2) Patch only

**Prompt**

```text
Apply the approved plan to add cancellation support.
Modify only the listed files.
Return concise summary + commands run.
```

**Expected artifact**
- Concrete code/doc patch in specified files.
- Commit-ready changes + verification commands.

### 3) Review only

**Prompt**

```text
Review this diff for architecture, typing, tests, and security.
Do not change code. Provide must-fix vs should-fix findings.
```

**Expected artifact**
- Structured review report.
- No file edits.
