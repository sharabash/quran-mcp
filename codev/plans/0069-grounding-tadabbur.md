# Plan: Permit Contemplative Reflection (Tadabbur) in Grounding Rules

## Metadata
- **ID**: plan-2026-03-26-grounding-tadabbur
- **Status**: implemented
- **Specification**: codev/specs/0069-grounding-tadabbur.md
- **Created**: 2026-03-26

## Executive Summary

Policy text changes across 4 files to add a recognized "Contemplative Reflection" mode alongside Citation and Attribution. No code changes. Single phase.

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "policy-text", "title": "Phase 1: Policy Text Revisions"}
  ]
}
```

## Phase 1: Policy Text Revisions
**Dependencies**: None

### Deliverables
- [x] `src/quran_mcp/assets/GROUNDING_RULES.md` — revised
- [x] `src/quran_mcp/assets/SKILL.md` — revised
- [x] `src/quran_mcp/server.py` — revised (one sentence)
- [x] `src/quran_mcp/middleware/tool_instructions.py` — revised (TAFSIR_INSTRUCTION)

### Acceptance Criteria
- [x] Core prohibition retains "interpret" and "summarize" — unweakened
- [x] Engagement Modes section present with 3 modes + guardrails
- [x] Reflection requires fetched text prerequisite
- [x] "tool-verified" not "tool-verifiable"
- [x] server.py synchronized with GROUNDING_RULES.md
- [x] TAFSIR_INSTRUCTION encourages tadabbur engagement
- [x] One label format (Applied Reasoning Disclaimer with qualifier)
- [x] All regression test cases from spec would pass
