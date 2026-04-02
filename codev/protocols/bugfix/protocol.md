# BUGFIX Protocol

## Overview

BUGFIX is a lightweight protocol for investigating and resolving bugs that require more than a trivial fix. It provides structure without the overhead of full SPIR phases.

**Core Principle**: Understand before you fix. Document what you learn.

## When to Use BUGFIX

Use BUGFIX when:
- Root cause is unknown and requires investigation
- Bug affects multiple files or components
- Bug is a regression from a dependency upgrade
- User-reported issue with unclear reproduction steps
- Fix requires understanding system behavior first

**Skip BUGFIX** (just fix it) when:
- Root cause is obvious (typo, missing import, etc.)
- One-line fix with no investigation needed
- You've fixed this exact issue before

## Workflow

```
1. TRIAGE    → Create bead, reproduce issue, document symptoms
     ↓
2. DIAGNOSE  → Find root cause, document investigation
     ↓
3. FIX       → Implement fix, run tests
     ↓
4. VERIFY    → Confirm fix works, check for regressions
     ↓
5. DOCUMENT  → Write bugfix report, close bead
```

## Phase Details

### 1. TRIAGE

**Goal**: Understand and reproduce the bug.

**Actions**:
1. Create a bead with `--type=bug`
2. Capture the error message/stack trace
3. Identify affected components
4. Reproduce the issue locally if possible
5. Document reproduction steps

**Output**: Bead created with initial symptoms documented.

### 2. DIAGNOSE

**Goal**: Find the root cause.

**Actions**:
1. Read relevant code (don't guess!)
2. Check recent changes: `git log --oneline -20 -- <affected-files>`
3. Check dependency changes if relevant
4. Form hypothesis about root cause
5. Verify hypothesis with evidence

**Tools**:
- `git blame` - who changed what
- `git log -p` - what changed
- `grep`/`Glob` - find related code
- Tests - verify behavior

**Output**: Root cause identified with evidence.

### 3. FIX

**Goal**: Implement the correct fix.

**Actions**:
1. Choose the architecturally correct solution (no band-aids)
2. Make minimal changes to fix the issue
3. Run existing tests
4. Add regression test if appropriate

**Principles**:
- Fix the root cause, not symptoms
- Don't refactor unrelated code
- Keep the diff focused

**Output**: Code changes that fix the bug.

### 4. VERIFY

**Goal**: Confirm the fix works and doesn't break anything.

**Actions**:
1. Verify the original issue is resolved
2. Run the full test suite
3. Test edge cases if applicable
4. Check for regressions in related functionality

**Output**: Passing tests, verified fix.

### 5. DOCUMENT

**Goal**: Capture learnings for future reference.

**Actions**:
1. Write bugfix report in `codev/bugfixes/NNNN-short-name.md`
2. Update bead with final notes
3. Close the bead
4. Commit with descriptive message

**Output**: Bugfix report, closed bead, committed fix.

---

## Bugfix Report Template

See `codev/protocols/bugfix/templates/bugfix-report.md`

Reports are stored in `codev/bugfixes/` with sequential numbering:
```
codev/bugfixes/
├── 0001-fastmcp-resource-return-type.md
├── 0002-api-timeout-handling.md
└── ...
```

---

## Commit Messages

```
[Bugfix] Fix resource return type for FastMCP 3.x

Root cause: FastMCP 3.x removed auto-serialization for resource dicts.
Fix: Return list[ResourceContent] instead of dict.

Bead: quran-mcp-0l4
```

---

## Multi-Agent Consultation

**Optional** for BUGFIX protocol. Use when:
- Root cause is unclear after initial investigation
- Fix involves architectural decisions
- You want a second opinion on the approach

`/codex:rescue` — "Investigate: <description>"

---

## Governance

| Document | Required? |
|----------|-----------|
| Bead | **Yes** |
| Bugfix Report | **Yes** (in `codev/bugfixes/`) |
| Multi-Agent Consultation | No (optional) |
| Spec/Plan/Review | No |

---

## Best Practices

1. **Reproduce first**: Don't fix what you can't reproduce
2. **Read before writing**: Understand the code before changing it
3. **Minimal diffs**: Only change what's needed for the fix
4. **Test coverage**: Add a regression test when practical
5. **Document learnings**: Future-you will thank present-you
6. **No band-aids**: Fix the root cause, not symptoms

---

## Anti-Patterns

1. **Fixing without understanding**: "I changed things until it worked"
2. **Scope creep**: Refactoring while bug-fixing
3. **Missing reproduction**: "It works on my machine"
4. **No documentation**: Fixing silently without capturing learnings
5. **Band-aid fixes**: Masking symptoms instead of fixing causes
