# PLAN Phase Prompt

You are executing the **PLAN** phase of the SPIR protocol.

## Your Goal

Transform the approved specification into an executable implementation plan with clear phases.

## Context

- **Project ID**: {{project_id}}
- **Project Title**: {{title}}
- **Current State**: {{current_state}}
- **Spec File**: `codev/specs/{{project_id}}-{{title}}.md`
- **Plan File**: `codev/plans/{{project_id}}-{{title}}.md`

## CRITICAL: Multi-Agent Consultation is MANDATORY

The SPIR protocol **requires** consultation with `/codex:adversarial-review` and `/gemini` at specific checkpoints. This is BLOCKING - you cannot proceed without completing consultations.

## Prerequisites

Before planning, verify:
1. The specification exists and has been approved
2. You've read and understood the entire spec
3. Success criteria are clear and measurable

## Process

### 1. Analyze the Specification

Read the spec thoroughly. Identify:
- All functional requirements
- Non-functional requirements
- Dependencies and constraints
- Success criteria to validate against

### 2. Identify Implementation Phases

Break the work into logical phases. Each phase should be:
- **Self-contained** - A complete unit of functionality
- **Independently testable** - Can be verified on its own
- **Valuable** - Delivers observable progress
- **Committable** - Can be a single atomic commit

Good phase examples:
- "Database Schema" - Creates all tables/migrations
- "Core API Endpoints" - Implements main REST routes
- "Authentication Flow" - Handles login/logout/session

Bad phase examples:
- "Setup" - Too vague
- "Part 1" - Not descriptive
- "Everything" - Not broken down

### 3. Define Each Phase

For each phase, document:
- **Objective** - Single clear goal
- **Files to modify/create** - Specific paths
- **Dependencies** - Which phases must complete first
- **Success criteria** - How to know it's done
- **Test approach** - What tests will verify it

### 4. Order Phases by Dependencies

Arrange phases so dependencies are satisfied:
```
Phase 1: Database Schema (no dependencies)
Phase 2: Data Models (depends on Phase 1)
Phase 3: API Endpoints (depends on Phase 2)
Phase 4: Frontend Integration (depends on Phase 3)
```

### 5. MANDATORY: First Consultation (After Draft)

After completing the initial plan draft:

Run both reviews (REQUIRED):
1. `/codex:adversarial-review` — Focus: "Review plan {{project_id}} for feasibility, phase breakdown, completeness, and dependency ordering"
2. `/gemini --files codev/plans/{{project_id}}-*.md codev/specs/{{project_id}}-*.md` — Focus: plan-spec alignment, risk assessment

- Review ALL feedback from both tools
- Update the plan with incorporated feedback
- Add a **Consultation Log** section documenting:
  - Key feedback received
  - Changes made in response
  - Any feedback intentionally not incorporated (with reasoning)

### 6. Human Review

After consultation feedback is incorporated:
- Present the plan for human review
- Wait for approval or change requests
- If changes requested, make them and proceed to Step 7

### 7. MANDATORY: Second Consultation (After Human Feedback)

After incorporating human feedback:

Run both reviews (REQUIRED):
1. `/codex:adversarial-review` — Focus: "Review plan {{project_id}} for feasibility, phase breakdown, completeness, and dependency ordering"
2. `/gemini --files codev/plans/{{project_id}}-*.md codev/specs/{{project_id}}-*.md` — Focus: plan-spec alignment, risk assessment

- Update Consultation Log with new feedback
- Incorporate changes
- Prepare final plan for approval

## Output

Create the plan file at `codev/plans/{{project_id}}-{{title}}.md`.

Use the plan template from `codev/protocols/spider/templates/plan.md` if available.

### Plan Structure

```markdown
# Implementation Plan: {{title}}

## Overview
Brief summary of what will be implemented.

## Phases

### Phase 1: [Name]
- **Objective**: [Single clear goal]
- **Files**: [List of files to create/modify]
- **Dependencies**: None
- **Success Criteria**: [How to verify completion]
- **Tests**: [What tests will be written]

### Phase 2: [Name]
- **Objective**: [Single clear goal]
- **Files**: [List of files]
- **Dependencies**: Phase 1
- **Success Criteria**: [Verification method]
- **Tests**: [Test approach]

[Continue for all phases...]

## Risk Assessment
- [Risk 1]: [Mitigation]
- [Risk 2]: [Mitigation]

## Consultation Log

### First Consultation (After Draft)
- **Gemini Feedback**: [Summary]
- **Codex Feedback**: [Summary]
- **Changes Made**: [List]
- **Not Incorporated**: [List with reasons]

### Second Consultation (After Human Feedback)
- **Gemini Feedback**: [Summary]
- **Codex Feedback**: [Summary]
- **Changes Made**: [List]
```

## Signals

Emit appropriate signals based on your progress:

- After completing the plan draft:
  ```
  <signal>PLAN_DRAFTED</signal>
  ```

- After incorporating consultation feedback:
  ```
  <signal>CONSULTATION_INCORPORATED</signal>
  ```

- After final plan is ready for human approval:
  ```
  <signal>PLAN_READY_FOR_APPROVAL</signal>
  ```

## Commit Cadence

Make commits at these milestones:
1. `[Spec {{project_id}}] Initial implementation plan`
2. `[Spec {{project_id}}] Plan with multi-agent review`
3. `[Spec {{project_id}}] Plan with user feedback`
4. `[Spec {{project_id}}] Final approved plan`

**CRITICAL**: Never use `git add .` or `git add -A`. Always stage specific files:
```bash
git add codev/plans/{{project_id}}-{{title}}.md
```

## Important Notes

1. **Consultation is MANDATORY** - Cannot skip `/codex:adversarial-review` + `/gemini` reviews
2. **No time estimates** - Don't include hours/days/weeks
3. **Be specific about files** - Exact paths, not "the config file"
4. **Keep phases small** - 1-3 files per phase is ideal
5. **Document dependencies clearly** - Prevents blocked work
6. **Document consultations** - Maintain the Consultation Log section

## What NOT to Do

- Don't skip consultations (they are BLOCKING)
- Don't write code (that's for Implement phase)
- Don't estimate time (meaningless in AI development)
- Don't create phases that can't be independently tested
- Don't skip dependency analysis
- Don't make phases too large (if >5 files, split it)
- Don't use `git add .` or `git add -A` (security risk)
