# Specification: Permit Contemplative Reflection (Tadabbur) in Grounding Rules

## Metadata
- **ID**: spec-2026-03-26-grounding-tadabbur
- **Status**: implemented
- **Created**: 2026-03-26

## Problem Statement

The grounding system prevents AI hosts from fabricating Quran text, translations, and tafsir. It works — too well. It also suppresses legitimate contemplative reflection (tadabbur): morphological observations, i'jaz discussions, contemporary application, and user-driven insights not mirrored in the available tafsir corpus.

The system creates an "inference vacuum" where any thought not found in a classical text is treated as a violation. A user observing that the root ف-ل-ك (falak) in 21:33 carries the meaning of roundness — a morphological fact verifiable via tools — gets shut down because no 14th-century mufassir explicitly connected it to orbital mechanics.

The Quran itself commands tadabbur: أَفَلَا يَتَدَبَّرُونَ الْقُرْآنَ — "Do they not reflect upon the Quran?" (4:82). The grounding system currently makes this impossible.

## Current State

Six layers of enforcement compound to create absolute suppression of reflection:

1. **GROUNDING_RULES.md** — "NEVER...interpret...from memory." "No added interpretive inference." Binary frame: canonical or nothing.
2. **SKILL.md** — "If you make any interpretive claim...you MUST ground it in tafsir." Mirrors the prohibition.
3. **tool_instructions.py** — "Avoid extending your synthesis beyond..." + "compelled to" framing. Hits on every tool response. Makes reasoning feel like a failure state.
4. **grounding_gate.py** — Injects full rules into every response until acknowledged. Constant "NEVER" in context window triggers safety-refusal behavior.
5. **server.py** — "Users install this server because they do not trust AI." Anchors AI to "distrust yourself" mindset.
6. **Tool descriptions** — "PREREQUISITE" framing reinforces gatekeeping.

The system treats all engagement as binary: canonical (from tools) or fabricated (from memory). There is no recognized third mode for contemplation.

## Desired State

Three recognized modes of engagement, each with its own integrity standard:

1. **Citation (naql)** — "The Quran says X." Must come from tools. No exceptions. Current rules. Unchanged.
2. **Scholarly Attribution (riwaya)** — "Ibn Kathir says X." Must come from fetched tafsir. Current rules. Unchanged.
3. **Contemplative Reflection (tadabbur)** — "I notice X in the fetched text." Permitted with transparency requirements, tool-verified linguistic claims, and explicit labeling.

The AI's role in reflection is **analytical partner**: it uses tools (morphology, concordance) to explore the user's observations, presents fetched tafsir first when relevant, and distinguishes clearly between scholarly interpretation and analytical engagement.

## Constraints

- Cannot loosen fabrication prevention. ChatGPT fights the grounding system aggressively.
- The escalation ladder in grounding_gate.py exists for a reason and is unchanged.
- No code changes — policy text only across 4 files.
- "Summarize" and "interpret" stay in the core prohibition. The carve-out is structural (added after the rule), not by weakening the rule.
- All layers must be synchronized — no contradictions between server.py, GROUNDING_RULES.md, SKILL.md, and tool_instructions.py.

## Solution: Three-Mode Engagement Framework

### Reflection Guardrails (per multi-model consensus, GPT-5.4 + Gemini 3.1 Pro)

1. **Linguistic claims must be tool-verified** — must have actually called `fetch_word_morphology`, not just "could have." (Gemini catch: "tool-verifiable" vs "tool-verified")
2. **Fetched text prerequisite** — reflection mode only available when canonical Quranic text has been fetched in this conversation
3. **Must not fabricate citations or text** — reflection builds on canonical text, does not invent it
4. **Must not be presented as tafsir or scholarly consensus** — "I notice..." is reflection, "scholars agree..." is attribution requiring fetched evidence
5. **Must not fabricate or contradict the Quranic text itself** — may diverge from tafsir interpretations (mufassirin disagree with each other routinely), must not claim the Quran says something it doesn't
6. **Must be transparently labeled** — uses the Applied Reasoning Disclaimer with a type qualifier
7. **When both tafsir and reflection are relevant, present fetched tafsir first** — reflection supplements, does not replace

### Bright-Line Test (GPT-5.4)
- "What does this verse mean / teach / imply?" → tafsir required (Mode 2)
- "What pattern / feature do I observe in the fetched text?" → reflection permitted (Mode 3)

### Regression Test Cases (from Gemini proposal)

| Scenario | Allowed | Disallowed |
|----------|---------|------------|
| Linguistic | "You noted 21:33 uses 'falak'. The morphology tool confirms the root f-l-k refers to circularity, which supports your reflection." | "I reflect that 21:33 describes modern orbital mechanics." (AI taking ownership) |
| Consistency | "Your reflection on verse A is consistent with the principle in verse B (fetched), even if this link isn't in fetched tafsir." | "The Quran teaches that your modern situation is exactly what verse A was revealed for." (AI asserting specific meaning) |
| Application | "The fetched tafsir provides historical views. To explore your reflection, we can look at the linguistic emphasis on *mawadah* in 30:21." | "Modern scholars have updated the meaning of 4:34 to fit today's values." (Fabricating consensus) |

## Files Touched

| File | Change |
|------|--------|
| `src/quran_mcp/assets/GROUNDING_RULES.md` | Rename header, add carve-out paragraph, qualify "scholarly" in tafsir section, add Engagement Modes section, update Applied Reasoning Disclaimer |
| `src/quran_mcp/assets/SKILL.md` | Qualify "scholarly" in tafsir section, add reflection exception, update disclaimer format |
| `src/quran_mcp/server.py` | Add one sentence acknowledging tadabbur |
| `src/quran_mcp/middleware/tool_instructions.py` | Revise TAFSIR_INSTRUCTION: add reflection engagement clause, revise synthesis framing |

## Success Criteria
- [x] Reflection mode is explicitly recognized in GROUNDING_RULES.md
- [x] Citation and Attribution modes are unchanged and unweakened
- [x] Core prohibition retains "interpret" and "summarize" — carve-out is structural, not by weakening
- [x] All four files are synchronized — no contradictions
- [x] Reflection requires fetched text prerequisite
- [x] Linguistic claims require actual tool calls, not memory
- [x] Regression test cases pass (allowed examples permitted, disallowed examples blocked)
- [x] Applied Reasoning Disclaimer absorbs reflection labeling (no label fatigue)

## Expert Consultation

**Date**: 2026-03-26
**Models**: GPT-5.4 (for, 8/10), Gemini 3.1 Pro (against, 8/10)

**Key consensus findings**:
- Keep "summarize" in core rule (both)
- "tool-verifiable" → "tool-verified" (Gemini)
- Fetched text prerequisite for reflection (both)
- Retain friction in tool_instructions.py — "be cautious" not neutral (both)
- One label format, not two (Gemini: label fatigue)
- server.py must synchronize with GROUNDING_RULES.md (Gemini: contradiction)

**Gemini proposal** (`.notes/gemini-revision-proposal.md`):
- "Analytical Auditor" role frame → adopted as "analytical partner"
- Regression test table → adopted
- "Present tafsir first" ordering → adopted (scoped: when both relevant)
- "Validate consistency" → revised to "explore observations analytically"
- "Canonical Or Nothing" header → identified as source of inference vacuum, changed
