# Spikes: De-risking Technical Unknowns

**Spikes are short, focused experiments that validate technical assumptions before full implementation.**

## What is a Spike?

The term comes from Extreme Programming (XP), coined in the late 1990s. The metaphor: a spike is like driving a railroad spike through all layers of a problem to see what's underneath. You're not building the whole foundation - you're just poking through to answer a specific question.

**Key characteristics:**
- **Time-boxed** - Typically 1-2 hours; check in if taking longer
- **Throwaway** - The code is discarded; only the knowledge is kept
- **Focused** - Answers ONE specific question
- **Reduces risk** - Done before committing to full implementation

| Type | Question |
|------|----------|
| Spike | "Can we?" / "Does it work?" |
| Implementation | "Build it" |

## Time-Boxing

**Spikes should typically take 1-2 hours.** If you're spending significantly longer, consider:

1. **Is the question too big?** Break it into smaller spikes
2. **Is the answer "not easily"?** That's valuable information - document it
3. **Do you need more time?** That's fine, but check in with the user first

Time-boxing helps prevent spikes from becoming open-ended research. The goal is a quick answer, not perfection.

## When to Use Spikes

Use spikes when a spec has:
- **Untested external APIs** - Will the API actually behave as documented?
- **Architectural uncertainty** - Will this pattern work for our use case?
- **Integration questions** - Can these components work together?
- **Performance unknowns** - Will this approach be fast enough?

**Rule of thumb:** If the spec says "we believe X will work" or "according to docs, Y should happen" - that's a spike candidate.

## Spike Structure

Store spikes in `codev/spikes/{spec-number}/`:

```
codev/spikes/
└── 0062/
    ├── spike-api-behavior.ts
    ├── spike-event-handoff.ts
    └── spike-storage-roundtrip.ts
```

Each spike file should:

```typescript
/**
 * Spike: [Clear Name]
 *
 * Purpose: [What assumption are we validating?]
 * Time Box: 1-2 hours
 *
 * Tests:
 * 1. [Specific test case]
 * 2. [Another test case]
 * 3. [Edge case]
 *
 * Run with: npx tsx codev/spikes/0062/spike-name.ts
 */

// Self-contained, runnable code that validates the assumption
// Mock/simulate infrastructure where needed
// Print clear PASS/FAIL for each test
```

## Spike Workflow

1. **Identify unknowns** during Plan phase - what could break our assumptions?
2. **Create spikes** for each high-risk unknown (1-2 hours each)
3. **Run spikes** and document results in spec/plan
4. **Adjust plan** based on spike findings
5. **Include spike results** in spec as "Research Findings"

## Example Spike Questions

| Unknown | Spike Purpose |
|---------|---------------|
| "Gemini 3 requires thought signatures" | Validate signature storage and replay works |
| "Two Inngest functions can hand off" | Test event emission and separate invocation |
| "Frontend handles sequence gaps" | Simulate gap and verify realignment |
| "Raw payload survives database round-trip" | Store and reconstruct exact API format |

## Spike vs Prototype vs POC

| Type | Scope | Output | Kept? | Time |
|------|-------|--------|-------|------|
| **Spike** | Single question | PASS/FAIL + learnings | No (throwaway) | 1-2 hours |
| **Prototype** | Feature shape | Working UI/flow | Sometimes | Days |
| **POC** | System viability | Minimal working system | Often becomes v1 | Weeks |

Spikes are deliberately disposable - they exist to answer a question, not to become production code.

## Build Exclusion

**Always exclude spikes from the project's TypeScript build:**

```json
// tsconfig.json
{
  "exclude": ["node_modules", "codev/spikes"]
}
```

Why:
- Spikes use experimental/mock code that may not compile cleanly
- Spikes may import packages not in production dependencies
- Keeps build fast and focused on production code
- Prevents spike code from accidentally shipping

Run spikes directly: `npx tsx codev/spikes/0062/spike-name.ts`
