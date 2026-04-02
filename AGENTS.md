# Agent Instructions

> **Note**: This file follows the [AGENTS.md standard](https://agents.md/) for cross-tool compatibility with Cursor, GitHub Copilot, and other AI coding assistants.

This document is the **canonical source of truth** for all AI coding agents working on this project. Read this file completely before starting any work.

---

## 1. Git Commit Attribution

AI coding agents MUST add minimal, factual attribution as the **last line** of the commit message based on available information:

**If model name AND version are known:**
```
Co-authored with AI: Claude Sonnet 4.5
```

**If only model name is known:**
```
Co-authored with AI: Claude
```

**If neither is known:** No attribution.

**Prohibited attribution styles:**
- Marketing language ("Generated with [Product Name]")
- Self-congratulatory phrasing
- Product links or promotional content
- Emoji or decorative elements

Attribution should be purely informational for human collaborators to understand the tool provenance of each commit.

**Example commit message:**
```
feat: Add user authentication system

Implements JWT-based authentication with refresh tokens.
Includes middleware for protected routes.

Co-authored with AI: Claude Sonnet 4.5
```

### Git Workflow

Never push to remote master without explicit human permission.

#### NEVER USE `git add -A` or `git add .`

**CRITICAL SECURITY REQUIREMENT - NO EXCEPTIONS**

**BANNED COMMANDS**:
```bash
git add -A        # FORBIDDEN
git add .         # FORBIDDEN
git add --all     # FORBIDDEN
```

**ALWAYS ADD FILES EXPLICITLY**:
```bash
# CORRECT
git add codev/specs/0001-feature.md
git add src/quran_mcp/mcp/tools/quran/fetch.py

# CORRECT - Specific patterns
git add codev/specs/*.md
```

### Commit Messages
```
[Spec 0001] Initial specification draft
[Spec 0001][Phase: feature] feat: Add new capability
```

### Branch Naming
```
spir/0001-feature-name/phase-name
```

---

## 2. Agent Startup Protocol

### Mandatory Reading

Before starting ANY work, agents MUST:

1. **Read this file completely** (AGENTS.md) - no partial reads via `head -n 100` or similar
2. **Read the full SPIR protocol** at `codev/protocols/spider/protocol.md` - this is authoritative
3. **Use templates exactly** from `codev/protocols/spider/templates/*.md` - no paraphrasing

### Protocol Authority Note

> **IMPORTANT**: SPIR behavior is governed by `codev/protocols/spider/protocol.md`. The summary below MUST be kept in sync with that file. If this summary and protocol.md ever conflict, **follow protocol.md**.

### Startup Confirmation (One-Time Per Session)

On first message in a new session, agents should confirm understanding by acknowledging they have read:
- AGENTS.md (this file)
- The applicable protocol (SPIR or TICK)
- Relevant templates

This confirmation is one-time per session, not required on every reply.

---

## 3. Codev Development Methodology

This project uses the **Codev development methodology** - a context-driven approach that treats natural language specifications as code.

### Available Protocols

| Protocol | Use Case | Location |
|----------|----------|----------|
| **SPIR** | Multi-phase development with multi-agent consultation | `codev/protocols/spider/protocol.md` |
| **TICK** | Fast autonomous implementation | `codev/protocols/tick/protocol.md` |
| **EXPERIMENT** | Disciplined experimentation | `codev/protocols/experiment/protocol.md` |
| **MAINTAIN** | Codebase maintenance | `codev/protocols/maintain/protocol.md` |
| **BUGFIX** | Structured bug investigation and resolution | `codev/protocols/bugfix/protocol.md` |

### Protocol Selection Guide

**Use SPIR for:**
- New features requiring architectural decisions
- Complex features requiring multiple phases
- Major refactoring or redesign work
- System design decisions
- Features with unclear requirements

**Use TICK for:**
- Small features (< 300 lines of code)
- Well-defined tasks with clear requirements
- Simple configuration changes

**Use BUGFIX for:**
- Bugs requiring investigation (root cause unknown)
- Bugs affecting multiple files or components
- Regressions from dependency upgrades
- Issues reported by users with unclear reproduction

**Skip formal protocols for:**
- Minor documentation fixes
- Trivial bug fixes (typos, obvious one-line fixes)
- Dependency updates (unless breaking changes)

### Key Locations

| Type | Location |
|------|----------|
| Protocols | `codev/protocols/` |
| Specifications | `codev/specs/` |
| Plans | `codev/plans/` |
| Reviews | `codev/reviews/` |

### File Naming Convention

Sequential numbering with descriptive names:
- Specification: `codev/specs/0001-feature-name.md`
- Plan: `codev/plans/0001-feature-name.md`
- Review: `codev/reviews/0001-feature-name.md`

### SPIR Protocol - Mandatory Workflow

#### S - Specify

1. Agent writes initial spec draft
2. COMMIT: "Initial specification draft"
3. Agent runs `/codex:adversarial-review` and `/gemini` for document review
4. Agent updates spec with feedback
5. COMMIT: "Specification with multi-agent review"
6. **STOP → USER REVIEWS**
7. User provides feedback (or approves)
8. Agent updates spec
9. COMMIT: "Specification with user feedback"
10. Second multi-agent consultation
11. Final updates
12. COMMIT: "Final approved specification"
13. **STOP → USER MUST SAY "proceed to planning"**

#### P - Plan

1. Agent writes initial plan
2. COMMIT: "Initial plan draft"
3. Agent runs `/codex:adversarial-review` and `/gemini` for document review
4. Agent updates plan with feedback
5. COMMIT: "Plan with multi-agent review"
6. **STOP → USER REVIEWS**
7. User provides feedback (or approves)
8. Agent updates plan
9. COMMIT: "Plan with user feedback"
10. Second multi-agent consultation
11. Final updates
12. COMMIT: "Final approved plan"
13. **STOP → USER MUST SAY "proceed to implementation"**

#### IDE Loop (per phase)

1. **I - Implement** → multi-agent consultation → fix feedback
2. **D - Defend** (tests) → multi-agent consultation → fix feedback
3. **E - Evaluate** → **STOP → USER APPROVES** → commit phase

**After each phase commit**: Agent MUST update checkboxes (`- [ ]` → `- [x]`) in both the **plan** (Deliverables, Acceptance Criteria for the completed phase) and the **spec** (any Success Criteria now satisfied). Unchecked boxes = incomplete work. Include these file edits in the phase commit.

#### R - Review

1. Create review document with lessons learned
2. Update protocol/docs based on learnings

### Hard Gates (MUST STOP AND WAIT)

These are non-negotiable checkpoints. **DO NOT PROCEED** without explicit user instruction:

| Gate | Trigger | Required User Action |
|------|---------|---------------------|
| **GATE 1** | After spec has multi-agent feedback | Wait for user review |
| **GATE 2** | After user approves spec | Wait for "proceed to planning" |
| **GATE 3** | After plan has multi-agent feedback | Wait for user review |
| **GATE 4** | After user approves plan | Wait for "proceed to implementation" |
| **GATE 5** | After each phase's Evaluate | Wait for user approval before commit |

### Multi-Agent Consultation

**DEFAULT**: Consultation is ENABLED with:
- **GPT-5 Codex** (`/codex:review` or `/codex:adversarial-review`): Primary reviewer for architecture, feasibility, and code quality
- **Gemini Pro** (`/gemini`): Secondary reviewer for completeness, edge cases, and alternative approaches

To disable: User must explicitly say "without multi-agent consultation"

### Critical Consultation Checkpoints

- After implementation → **STOP** → Run `/codex:review` and `/gemini` on the implementation
- After tests → **STOP** → Run `/codex:review` and `/gemini` on the test suite
- THEN present to user for evaluation

### Important Notes

1. **ALWAYS check protocol files** for detailed phase instructions
2. **Use provided templates** from protocol directories
3. **Document deviations** from plans with reasoning
4. **Create atomic commits** for each phase
5. **Maintain >90% test coverage** where possible

---

## 4. SDK/Library Integration Protocol

**CRITICAL PRINCIPLE**: When integrating any external SDK, library, or API client, operate from certainty, not assumptions. Inventing class names, method signatures, or data structures is a non-negotiable engineering failure.

### Verification Hierarchy (Follow in Order)

#### Level 1: Interactive Inspection (Primary Method - Fastest & Most Reliable)

Use an interactive Python shell to get definitive information about the installed package.

1. **Confirm Imports**:
   ```bash
   python -c "import goodmem_client"
   python -c "from goodmem_client.api import SpacesApi"
   ```

2. **Inspect Available Symbols**:
   ```bash
   python -c "import goodmem_client; print(dir(goodmem_client))"
   python -c "from goodmem_client.api import SpacesApi; print(dir(SpacesApi))"
   ```

3. **Verify Method Signatures**:
   ```bash
   python -c "import inspect; from goodmem_client.api import SpacesApi; print(inspect.signature(SpacesApi.create_space))"
   ```

4. **Inspect Data Models**:
   ```bash
   python -c "from goodmem_client.models import SpaceCreationRequest; print(SpaceCreationRequest.__annotations__)"
   ```

#### Level 2: Official Documentation

If interactive inspection is unclear or you need conceptual context:

- Use Context7 `resolve-library-id` and `query-docs` for up-to-date documentation
- Use WebFetch for official SDK documentation
- **Critical**: If docs conflict with Level 1 findings, trust the interactive inspection

#### Level 3: Source Code (Fallback for Complex Cases)

When details remain ambiguous (complex data models, unclear return types):

1. **Locate Package**: `.venv/lib/python*/site-packages/[package-name]/`
2. **Key Files**:
   - `__init__.py`: Top-level exports
   - `api/`: Client classes and methods
   - `models/`: Request/response data structures
3. **Verify**:
   - Method signatures (parameters, type hints, return types)
   - Data model field names and types
   - Response structures

### Pre-Integration Checklist

Before writing any integration code, verify:
- [ ] Class names exist (e.g., `SpacesApi` not `SpaceClient`)
- [ ] Method names are correct (e.g., `create_space` not `createSpace`)
- [ ] Parameter names match exactly (e.g., `space_creation_request` not `create_space_request`)
- [ ] Data model fields are correct (check actual class definition)
- [ ] Import paths are accurate
- [ ] Return types and response structures are verified

### Evidence Requirements for PRs

When introducing SDK integration code, PRs must include:

1. **Version Pin**: Exact package version from `pip show [package]` or lockfile
2. **Verification Output**: Copy/paste from Level 1 inspection showing:
   - Successful imports
   - Method signatures via `inspect.signature()`
   - Model annotations or `dir()` output
3. **Documentation Links**: Permalinks to official docs for the pinned version
4. **Probe Script** (for critical integrations): Add `scripts/verify_[sdk].py` that:
   - Imports all used classes
   - Prints signatures for all used methods
   - Runs in CI to catch regressions

### Enforcement

- **Merge Blocker**: PRs with unverified SDK usage will be blocked or reverted
- **Remediation**: If guessed API calls reach main:
  1. Revert immediately or open urgent fix PR
  2. Re-verify against installed version
  3. Add probe/test coverage
  4. Document verification evidence

### Why This Matters

Making up SDK calls wastes time, breaks production, and erodes trust. Taking 5 minutes to verify saves hours of debugging and prevents user-facing failures.

---

## 5. Project Architecture

### Package Structure

```
src/quran_mcp/
  __init__.py
  server.py                    # Entry point — the only Python at root
  mcp/                         # Client-facing MCP surface
    tools/                     #   Tool handlers (fetch_quran, search_tafsir, etc.)
    resources/                 #   MCP resources
    prompts/                   #   MCP prompts
  lib/                         # Business logic and utilities
    db/                        #   Database access
    editions/                  #   Edition registry
    documentation/             #   Documentation site generator
    settings.py                #   Configuration
    ...
  middleware/                   # MCP request pipeline
  apps/                        # Frontend apps
  assets/                      # Static files
```

The `mcp/` namespace separates **client-visible MCP surface** from **internal implementation**. `lib/` is business logic. `middleware/` wraps the ASGI application.

### Running the server

```bash
# Development
fastmcp dev src/quran_mcp/server.py

# Production
# reads port from config.yml via settings
python -m quran_mcp.server
```

---

## 6. Human-in-the-Loop Principle

### THE PRIMARY RULE

**If what you're finding would cause you to deviate from the spec, make a judgment call the spec doesn't cover, or you discover something that changes your understanding of the problem — STOP and surface it to the user. Don't adapt silently.**

This rule is non-negotiable and overrides any bias toward autonomous progress.

### What Counts As "Stop and Surface"

These are examples, not an exhaustive list. Use judgment — when in doubt, surface it.

- The approach that worked for one component does not transfer to another (different structure, different conventions)
- You're about to make a schema change or add a table/model not in the approved plan
- You want to use a library, service, or approach not mentioned in the spec
- Any situation where you're choosing between two reasonable approaches and the spec doesn't prescribe which
- Any situation where you're silently skipping or deferring something the spec says to do

### How to Surface

When you stop, present:
1. **What you found** — concrete, not abstract. Show examples.
2. **Why it matters** — what decision does this require?
3. **Your recommendation** — if you have one. It's okay to say "I don't know, here's the tradeoff."
4. **Then wait.** Don't proceed until you get direction.

---

## 7. Other Rules

- **Thoroughness over speed**: Read every line of code before modifying it. Trace every reference before removing anything. Verify your work against the original request item by item. Do not optimize for completion speed. When in doubt, ask.
- **Elegance over expediency**: Prefer the clean, architecturally correct solution. Naming matters — consistent, unambiguous, systematic. File placement matters — reason about ownership before deciding where code goes. If two approaches exist and one is simpler but less principled, choose the principled one.
- **Answer questions directly**: When the user questions a decision or asks "why", explain your reasoning. Questions are questions, not implicit requests to change something. Don't change code when asked "why did you do X."
- **Answer your own questions**: Never ask the user something you can answer by reading the codebase. Read the code first. Only ask when the answer requires user intent or preference.
- **Follow instructions literally**: Don't silently reduce scope. If told "for every file" or "thoroughly", do it for every file, thoroughly. Disclose if you skip anything. Don't claim "done" until every item on the request is covered.
- **No shortcut hacks**: Always propose the architecturally correct solution first. Do not implement quick workarounds that create technical debt. If the proper fix requires more effort, explain that upfront and let the user decide.
- **Public repo discipline**: Only commit what a public forker needs. Ask "would a forker need this?" before adding any file.
- **Know where things go**:
  - **`docs/`** — User-facing documentation only. Setup guides, architecture overviews, things a stranger reads. Never dump agent analysis here.
  - **`.insights/`** — Committed institutional memory (see Section 8). Things that steer future decisions — domain knowledge a future session can't derive from reading the code alone.
  - **`.notes/`** — Gitignored scratch. Ephemeral agent working notes, TODO lists, draft plans, conversation context that doesn't need to survive across contributors. Not committed, not shared.
- Properly explore the project structure before making any architectural decisions.
- **Integration and E2E tests MUST go in `tests/integration/`** — NEVER put them in the main `tests/` folder. Unit tests (with mocks) go in `tests/`. Integration tests (hitting real external services) and E2E tests (through full MCP stack) go in `tests/integration/`.
- **Directory READMEs**: When adding or removing files in `tests/`, `scripts/`, or `docs/` (or their subdirectories), update the directory's `README.md` file registry table. Each entry has three columns: **File**, **Covers**, **Purpose**. Keep entries one-line. The README is a living index — if it doesn't match the directory, it's wrong.

---

## 8. Insights — Institutional Memory

The `.insights/` directory is the project's institutional memory. It's not a write-only log — it's a system that agents actively READ before starting work.

```
.insights/
  REGISTRY.md                   # compact index — ALWAYS read before starting work
  {topic}/
    {description}.md            # detail file for a specific learning
```

### REGISTRY.md Format

Every learning gets a one-line entry in the registry:

```markdown
| # | Date | Tags | Summary | Detail File |
|---|------|------|---------|-------------|
| 1 | 2026-03-22 | goodmem, client-behavior | ChatGPT ignores grounding rules through structuredContent — only reads tool descriptions | .insights/grounding/chatgpt-structured-content.md |
```

### What belongs here

Things that steer future decisions — domain knowledge you can't derive from reading the code alone:
- Edition quirks (missing fields, wrong attribution, pagination anomalies)
- Client behavior differences (what ChatGPT does vs Claude, MCP App host limitations)
- GoodMem operational knowledge (space configuration, embedder behavior, reranker tuning)
- Production discoveries (grounding bypass patterns, rate limit tuning from real traffic)
- Data quality issues (corpus gaps, translation coverage holes, attribution problems)

### What does NOT belong here

- Things the code already shows (removed dead code, refactored modules)
- Process lessons ("we should have done X") — those go in AGENTS.md rules
- Changelogs — that's git history
- Agent scratch work — that goes in `.notes/`

### Rules

1. **Before starting work**: Read `.insights/REGISTRY.md`. Pull in detail files whose tags match your task.
2. **When you discover something non-obvious**: Surface it to the user and propose it as an insight. Do not write to `.insights/` without user approval. Actively evaluate whether a finding is insight-worthy — but let the user decide.
3. **During SPIR Review**: Propose registry updates with learnings from the completed spec. User approves before writing.
4. **Tag vocabulary**: Use these tags (extend when genuinely needed): `goodmem`, `editions`, `grounding`, `client-behavior`, `data-quality`, `config`, `middleware`, `performance`.
5. **Registry size**: If > 100 entries, archive entries older than 30 days to `REGISTRY-ARCHIVE.md`.

---

## 9. Data Sources

All Quran text, translations, and tafsir commentary served by this project are sourced from [Quran Foundation](https://quran.foundation) projects, including [quran.com](https://quran.com) and [nuqayah.com](https://nuqayah.com). This server does not claim ownership over any of this content — see the [License](LICENSE.md) (Section 2: Scope and Data) for details.

---

## 10. Further Reading

### Key Directories
- `codev/protocols/` - Development protocols (SPIR, TICK, EXPERIMENT, MAINTAIN, BUGFIX)
- `codev/specs/`, `codev/plans/`, `codev/reviews/` - Feature documentation

### Quick Links

| Resource | Description |
|----------|-------------|
| [SPIR Protocol](codev/protocols/spider/protocol.md) | Full multi-agent development protocol |
| [SPIR Templates](codev/protocols/spider/templates/) | Spec, plan, and review templates |
