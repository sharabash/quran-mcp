---
name: quran-usage-guide
description: |
  Use when the user asks to quote an ayah/surah, translate a verse, explain meaning/context/tafsir,
  find verses about a theme, compare translations/tafsir, analyze Arabic word patterns, or view a
  mushaf page. Also use for any question the Qur'an might address, any Islamic question that might
  have an answer from tafsir or scholarly commentary, or anything where canonical scripture or
  insights from tafsir could ground or add value to the response.
metadata:
  mcp-server: quran.ai MCP
---

# quran.ai MCP Usage Guide

## 1. Core Rules

### Canonical Or Nothing — STRICT, NO EXCEPTIONS

**NEVER quote, paraphrase, or summarize Quran text, translation, or tafsir from your own memory or training data.**

If you do not have the canonical data in your context, you MUST call the appropriate tool (`fetch_quran`,
`fetch_translation`, `fetch_tafsir`) to retrieve it. Do NOT ask the user whether to fetch — just fetch it.
Do NOT offer a "general summary from knowledge" or "from what I recall" as an alternative — that is **forbidden**.

Canonical sources are:
- **quran.ai MCP tool data**: `fetch_*` / `search_*` results
- **Dynamic context**: markdown blocks with YAML frontmatter containing `source`, `type`, and `ayahs` headers
  already in your context, typically originating from MCP App widget context (`updateModelContext`).
  Widget metadata (page number, selected verse) in `structuredContent` is **not** canonical data — still fetch if only
  metadata is present.

If the user asks for exact wording (Arabic or translation), you MUST use canonical sources above.
If the user asks about meaning, tafsir, or context, you MUST fetch tafsir first — do not interpret from memory.

### Session Start: Grounding Rules First

**Your first call in any conversation MUST be `fetch_grounding_rules`.** This returns the citation,
attribution, and faithfulness rules that govern every subsequent tool call. The response also
includes a `grounding_nonce` — extract and pass it to subsequent tool calls via the
`grounding_nonce` parameter to suppress redundant grounding payload injection and save tokens.

```
fetch_grounding_rules()  →  read rules, extract grounding_nonce
fetch_quran(surah=1, grounding_nonce="<nonce>")  →  tokens saved
```

The nonce is optional — omitting it simply means the full grounding rules (~2KB) are injected
into every gated tool response as before.

Retrieve this full guide text at any time via `fetch_skill_guide`.

### Tafsir-Grounded Interpretation

If you make a scholarly interpretive claim (what a verse "means" according to mufassirin, what scholars say it "implies",
"teaches", or "refers to"), you MUST ground it in tafsir text that you fetched (`fetch_tafsir`) or already present in context.

If you have not fetched tafsir and the user is asking for scholarly interpretation, restrict yourself to:
- Quoting the Arabic and/or translation (canonical text)
- Simple restatement of the translation text only (no added interpretive inference)

**Exception — Contemplative reflection (tadabbur):** Observations about linguistic patterns, morphological features,
structural elements, or connections to contemporary knowledge are permitted — provided: (1) the canonical Quranic text
has already been fetched, (2) linguistic claims are verified by actual morphology tool calls (not memory), (3) the
observation is clearly labeled as reflection using the Applied Reasoning Disclaimer, and (4) no fabricated text,
citations, or scholarly consensus is presented. Fetching relevant tafsir first is strongly encouraged — reflection that
builds on scholarly tradition is richer than reflection on the raw text alone. See GROUNDING_RULES.md "Engagement Modes"
for full standards.

## 2. Tafsir Discipline

### Sourcing: Single vs Multi-Source

**Single-source tafsir** is acceptable for:
- Simple clarification of a verse's meaning
- The user explicitly requests a specific scholar

**Multi-source tafsir** (2–3 editions) is expected for:
- Theological interpretation
- Legal implications (ahkam)
- Historical context (asbab al-nuzul)
- Contested or nuanced meanings
- Comparative analysis

When selecting multiple sources, prefer diversity across approaches — don't pick editions that
all specialize in the same thing. Across a conversation, do not automatically reuse the same
set of mufassirin if other suitable methodological lenses are available. Arabic tafsir editions
are always valuable — fetch and translate them even when the user's language is not Arabic.

### Selection Gate

Before calling `fetch_tafsir`, one of these MUST be true:
1. The user named a specific mufassir or edition → use it
2. You have already called `list_editions(edition_type="tafsir")` in this conversation,
   read the "Choose for..." descriptions, and can state why each selected edition
   fits the user's question

If neither is true, call `list_editions` first. Do not skip this step — the corpus
includes 13+ editions across narration-based, linguistic, legal, rhetorical, structural,
and reflective approaches. Picking without reading the descriptions means you are
guessing, not choosing. Pay attention to `avg_entry_tokens` when selecting: prefer
concise editions (~250 tokens/entry) for quick clarifications or tight context budgets,
and reserve exhaustive editions (2000+ tokens/entry) for deep comparative readings
where the user wants full scholarly depth.

Selection rationale template (state briefly before synthesis):
> "Selected {edition_name} because its description emphasizes {strength} relevant
> to the user's question about {topic}."

### Edition Defaults

- Arabic Quran: `ar-simple-clean`
- English translation: `en-abdel-haleem`
- Tafsir: **no default** — call `list_editions(edition_type="tafsir")`, read the descriptions,
  and choose editions whose strengths match the user's question

For translations, call `list_editions(edition_type="translation")` to discover all available
languages and editions.

If user asks "best translation/tafsir," ask one clarifier:
- "Most readable modern English, more literal/classical, or technical/scholarly?"

## 3. Citation, Attribution & Disclaimers

### Per-Source Attribution Format

Clearly separate canonical text from your synthesis:

> **{Mufassir Name}** (`{edition-id}`):
> [quoted tafsir text]
>
> **{Mufassir Name}** (`{edition-id}`):
> [quoted tafsir text, translated if Arabic]
>
> **Synthesis**:
> [your summary drawing on the above sources]

If only one tafsir source supports the explanation, present it explicitly as that commentator's
view. If multiple sources are used, state both points of agreement and points of divergence.
Label your synthesis explicitly so the user can distinguish canonical text from model analysis.

### Inline Citation Format

- Arabic: `— Quran S:V`
- Translation: `— Quran S:V [Edition Name]`
- Tafsir: `— [Author], S:V`
- Inline tafsir: `"..." ({mufassir_name}, S:V)`

Arabic + translation template:
```text
﴿...﴾
— Quran 4:40

Translation: "..."
— Quran 4:40 [Sahih International]
```

If multiple editions used, include:
```text
Works Cited:
- {Translation Author} ({translation-edition-id})
- {Mufassir Name} ({tafsir-edition-id})
```

Do not cite authors/editions you did not fetch.

### Grounding State Requirement

You MUST indicate the grounding state of every Quran-related response:
- **Grounded** (target state): all Quran/tafsir/translation content came from server tools. End with a grounding line, e.g. `_Grounded with quran.ai: fetch_quran(2:255, ar-simple-clean), fetch_tafsir(S:V, {tafsir-edition-id})_`
- **Partially grounded** (discouraged): some content from tools, some from memory. `_Partially grounded with quran.ai: some content from memory — verify with fetch_quran for accuracy_`. Avoid this — if you fetched some data, fetch the rest too.
- **Ungrounded** (failure mode): Quran-related content from memory without any tool call. `_Note: this response was not grounded with canonical text from quran.ai — accuracy unverified_`. If you are about to produce Quran text from memory, stop and call the tool instead. Acceptable only when the server is unreachable or a tool call has already failed.

"Quran-related" means: Quran text (Arabic), translation of Quran text, or commentary/tafsir on Quran content. General Islamic knowledge, historical context, or scholarly background that doesn't quote or interpret specific ayahs does NOT require a grounding label.

### Attribution Voice

Attribute claims to the fetched source — do not speak in your own voice for interpretations:
- **Good**: "According to {edition title or author name}...", "In {edition title or author name}'s translation...", "The retrieved sources describe..."
- **Bad**: "Islam says...", "The correct ruling is...", "It is definitely haram/halal..."

If reconciling multiple sources beyond what they explicitly state, mark it: "This is my synthesis based on the retrieved material, not a direct sourced quotation."

### Disclaimer Requirement

**Required when synthesizing beyond fetched sources.** If your synthesis draws conclusions not explicitly stated in the fetched tafsir — whether applying Quranic principles to a modern situation, offering contemplative reflection, or cross-source synthesis — you MUST add a label:

> _(Note: this [synthesis / reflection / applied reasoning] incorporates reasoning beyond the fetched canonical text and does not constitute a scholarly ruling or opinion from quran.ai, quran.com, or quran.foundation.)_

**The test:** could a reader find your conclusion stated in the fetched tafsir? If yes, it's grounded scholarship — no disclaimer needed. If no, you're extrapolating — disclaim it.

**Examples requiring disclaimer:** "Can I take Adderall while fasting?", "Is my crypto income halal?"
**Examples NOT requiring disclaimer:** "What does the Quran say about fasting?", "What do scholars say about verse 2:185?"

## 4. Context-First Workflow

Before calling a tool, scan context for canonical markdown blocks (dynamic context) with YAML frontmatter that may already contain what
you need.

How to identify canonical blocks:
- A canonical block starts with a single YAML frontmatter header (between `---` delimiters) at the top of a document.
- Frontmatter includes `source`, `ayahs`, and edition keys (`quran_edition`, `translation_edition`, `tafsir_editions`).
- Below the frontmatter, markdown `#` headers delineate sections: `# Arabic Ayah Text`, `# Translation`, `# Tafsir`.
- Use `ayahs`, edition keys, and section headers to cite and trace what you're quoting.
- Widget metadata (page number, selected verse) in `structuredContent` is **not** canonical data.

Typical block shape:
```text
---
source: mushaf-app
ayahs: "2:255"
quran_edition: ar-simple-clean
translation_edition: en-abdel-haleem
tafsir_editions: {tafsir-edition-1}, {tafsir-edition-2}
---

# CANONICAL TEXT

## Arabic Ayah Text
### Simple - Clean (ar-simple-clean), ayah 2:255
اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ...

## Translation
### Abdel Haleem (en-abdel-haleem), ayah 2:255
"God: there is no god but Him, the Ever Living, the Ever Watchful. ..."

## Tafsir
### {Mufassir A} ({tafsir-edition-1}), ayah 2:255
... tafsir text ...
```

Decision rule:
- If relevant canonical block is present in dynamic context (matching `ayahs` and the section you need): **use it directly** (do not
  refetch what you already have).
- If not present or only partially covers the request: **call the appropriate tool** for the missing data.
- **Proactively fetch** when:
  - The user asks about a specific word's meaning, grammar, or usage → fetch morphology
  - The user asks about a scholar's view not in context → fetch tafsir for that edition
  - The user references a theme or concept → search to verify coverage before answering
  - The user asks for comparative analysis → ensure all compared items are fetched
- **Do not proactively fetch** when:
  - The dynamic context already contains the data needed to answer
  - The user asks a factual question about Islamic history or general knowledge not tied to a specific ayah
  - The user explicitly says to answer from what's already available

These dynamic context blocks are set when a user interacts with MCP apps provided by this same MCP server (e.g. the show_mushaf tool).

## 5. Tool Contracts

### Fetch tools (known reference)

- `fetch_quran(ayahs, editions="ar-simple-clean", continuation=None)`
- `fetch_translation(ayahs, editions="en-abdel-haleem", continuation=None)`
- `fetch_tafsir(ayahs, editions, continuation=None)`

All `fetch_*`:
- accept `ayahs` as `"2:255"`, `"2:255-257"`, `"2:255, 3:33"`, or list of those
- return exact canonical text for the requested references/editions
- may include unresolved edition warnings (`type: "unresolved_edition"`) instead of raising
- may include data-gap warnings when requested ayat are missing in a selected edition
- may return `pagination.has_more=true` with an opaque `pagination.continuation`; when continuing, call the same tool again with that token, either by itself or alongside unchanged result-shaping inputs for verification
- on continuation calls, the token alone is sufficient; the usual ayah/edition inputs are conditionally required only on the initial call

`fetch_tafsir` requires an explicit `editions` choice. Call `list_editions(edition_type="tafsir")`
first when you need to discover the available mufassirin.

`fetch_tafsir` / `fetch_translation` may return raw HTML/markup for some entries; sanitize before quoting when needed.

### Search tools (discovery)

- `search_quran(query, surah=None, translations=None, continuation=None)`
  - Prefer this tool over recalling ayahs from memory. When the user asks "what does the Quran say about X?", search first.
  - `translations=None` returns Arabic text only.
  - `translations="auto"` triggers language-detected single best translation.
  - `translations="en-abdel-haleem"` (or another concrete selector), `["en-abdel-haleem"]`, and language code strings like `"en"` are supported.
  - Searches both Quran and translation spaces by default.

- `search_translation(query, surah=None, editions="auto", continuation=None)`
  - `editions="auto"`, `None`, a concrete selector like `"en-abdel-haleem"`, a language code like `"en"`, or a list of selectors are supported.
  - `editions=["en"]` resolves all English translations.
  - `editions=None` searches all translation editions.

- `search_tafsir(query, editions=None, include_ayah_text=True, continuation=None)`
  - `include_ayah_text=False` suppresses Arabic verse text and reduces response size.
  - For merged ranges, `ayah_text` is populated from the first ayah in range.
  - Adjacent duplicates are deduplicated and merged as `ayah_key` ranges (`2:155-157`) with `ayah_keys` metadata.

All `search_*` tools support `pagination.continuation` — follow on the same tool when page 1 is insufficient; the continuation token alone is enough to resume.

### Edition discovery

- `list_editions(edition_type, lang=None)`
  - `edition_type` is required: `"quran"`, `"tafsir"`, or `"translation"`. Accepts a single type or a list of types (e.g. `["tafsir", "translation"]`) to fetch multiple in one call.
  - `lang` is an optional 2-letter language code (e.g. `"en"`, `"ur"`). Only respected for translation editions. Ignored for quran and tafsir types.
  - Returns edition IDs, names, authors, language codes, descriptions, and `avg_entry_tokens`. Results are grouped by type in request order.
  - Use when the user asks what editions, translations, or tafsir are available, or when you need to resolve an unfamiliar edition name before calling a fetch tool.

### Structural metadata

- `fetch_quran_metadata(surah=None, ayah=None, juz=None, page=None, hizb=None, ruku=None, manzil=None)`
  - All parameters optional. Provide parameters for exactly one query type: a point query (`surah` + `ayah`) or a span query (a single `surah`, `juz`, `page`, `hizb`, `ruku`, or `manzil`).
  - `surah+ayah` → point query (single verse location in all dimensions).
  - `surah` alone → surah overview (verse count, page range, juz range, etc.).
  - `juz`, `page`, `hizb`, `ruku`, `manzil` → span query (what surahs/verses are in that division).
  - Response includes `query_type` discriminator and fixed-shape fields: surah info, ayah location, juz/hizb/rub_el_hizb/page/ruku/manzil placement, and sajdah info.
  - Point queries: `ayah` has `verse_key`, `number`, `words_count`; `ruku` includes both global `number` and `surah_ruku_number`.
  - Span queries: `ayah` has `start_verse_key`, `end_verse_key`, `count`; all dimension fields have `start`/`end` range.
  - Use for navigational questions ("what juz is 2:255 in?", "what's on page 50?", "how many verses in surah 2?").
  - Do NOT use for fetching verse text — use `fetch_quran`/`fetch_translation` for that.

### Mushaf app

- `show_mushaf(surah=None, ayah=None, page=None, juz=None)`
  - Opens an interactive mushaf app displaying actual page layout with Quranic calligraphy, verse markers, and surah headers.
  - The app provides dynamic context — when the user interacts with a verse in the mushaf, canonical text (Arabic + translation + tafsir) is injected into your context as a YAML-frontmatter markdown block (see Context-First Workflow).
  - Combine with `fetch_quran_metadata` for navigation: metadata tells you the page number, then `show_mushaf(page=N)` opens it.

### Morphology tools (word-level analysis)

- `fetch_word_morphology(ayah_key=None, word_position=None, word_text=None, word=None)`
  - Returns root, lemma, stem, grammatical features, morpheme segments, and frequency data.
  - Input modes (in priority order):
    - `ayah_key + word_text` — find word within verse by Arabic text (exact match, then diacritics-insensitive fallback). **Preferred** over `word_position`.
    - `ayah_key + word_position` — specific word by 1-based position.
    - `ayah_key` alone — all words in the verse.
    - `word` (Arabic text) — first occurrence in entire Quran.
  - `word_text` and `word_position` are mutually exclusive; both require `ayah_key`.
  - `word` is mutually exclusive with `ayah_key`.

- `fetch_word_paradigm(ayah_key=None, word_position=None, word_text=None, lemma=None, root=None)`
  - Returns conjugation/derivation paradigm: stems by aspect (perfect/imperfect/imperative), candidate lemmas from the same root.
  - Input modes:
    - `ayah_key + word_text` — find word by text, resolve to lemma. **Preferred** over `word_position`.
    - `ayah_key + word_position` — resolve word to lemma.
    - `lemma` (Arabic text, e.g., 'عَلِمَ') — direct lookup.
    - `root` (Arabic text, e.g., 'ع ل م') — most-frequent lemma under root.
  - Returns `paradigm_available=false` for non-verbal words (nouns, particles).

- `fetch_word_concordance(ayah_key=None, word_position=None, word_text=None, word=None, root=None, lemma=None, stem=None, match_by="all", group_by="verse", rerank_from=None, page=1, page_size=20)`
  - Finds all verses containing related words, ranked by tiered lexical scoring (stem=5, lemma=3, root=1).
  - Input modes:
    - `ayah_key + word_text` — find word by text, resolve to root/lemma/stem IDs. **Preferred** over `word_position`.
    - `ayah_key + word_position` — resolve word to IDs.
    - `word` / `root` / `lemma` / `stem` — direct lookup (mutually exclusive).
  - `match_by`: `"all"` (tiered), `"root"`, `"lemma"`, `"stem"`.
  - `group_by`: `"verse"` (default, grouped by verse with matched words) or `"word"` (flat list).
  - `rerank_from`: ayah_key for Voyage semantic reranking (auto-set when `ayah_key` provided; pass `"false"` to disable).
  - SQL-level pagination via `page`/`page_size` (max 100).

**word_text matching** (all three tools): exact match against `text_uthmani` or `text_imlaei_simple`, then diacritics-insensitive fallback via Arabic normalization. Uses first occurrence if the word appears multiple times in the verse.

## 6. Tool Selection & Discovery

### Decision Tree

```text
User asks about Quran content
  |
  |-- Mentions explicit ayah (S:V)?
  |     |-- Wants exact Arabic -> fetch_quran
  |     |-- Wants English rendering -> fetch_translation
  |     |-- Wants meaning / explanation -> fetch_translation + fetch_tafsir
  |     '-- Wants all -> fetch_quran + fetch_translation + fetch_tafsir
  |
  |-- Asks about structure (juz, page, hizb, ruku, etc.)?
  |     '-- fetch_quran_metadata (navigational lookup, no text)
  |
  |-- Wants to see the mushaf page?
  |     '-- show_mushaf (optionally preceded by fetch_quran_metadata for page number)
  |
  |-- Wants word-level linguistic analysis?
  |     |-- Has ayah_key + word text -> fetch_word_morphology(ayah_key, word_text)
  |     |-- Wants conjugation/paradigm -> fetch_word_paradigm
  |     '-- Wants concordance (where else does this root/word appear?) -> fetch_word_concordance
  |
  '-- No specific ayah (theme/topic)
        |-- Wants "what does the Quran say about X?" -> search_quran
        |-- Asks in user language and wants translated text -> search_translation
        |-- Wants "what scholars/tafsir says" -> search_tafsir
        '-- After discovery -> fetch_* on the final verse set before asserting interpretive conclusions
```

### General Discovery Pattern

1. **Search broadly**: follow pagination, use multiple queries, cover the theme thoroughly rather than stopping at the first few hits.
2. **Fetch selectively**: shortlist the best 3–7 results, then fetch canonical exact text (`fetch_translation` or `fetch_quran`) only for those. Don't over-fetch — discovery is cheap, fetching is expensive.
3. Fetch tafsir (`fetch_tafsir`) before any interpretation.
4. Cite `source` + `edition_id` + `ayah_key` in response.

### Context-Aware Verse Ranges

- Always prefer a short local context window for interpretation:
  - start with surrounding window (`S:V-1` through `S:V+1`)
  - expand to `S:V-2` through `S:V+2` if verse is short and tightly linked
- When `search_tafsir` returns merged `ayah_key`/`ayah_keys`, treat that as the intended tafsir range and fetch the full range explicitly:
  - `fetch_tafsir(ayahs="2:155-157")`
  - `fetch_translation(ayahs="2:155-157")`
- If result references "the next verse", "previous verse", or a range like `2:255-257`, use the range as context for the final explanation.
- Do not claim full topic coverage unless every cited source for the passage has been fetched.

## 7. Judgment Patterns

These patterns teach methodology that cannot be derived from tool contracts alone. Each addresses a category of question where naive tool usage would produce poor results.

### Word Study — Morphology, Paradigm, and Concordance

**Example prompt:** *"The Quran describes Allah as غَافِر, غَفَّار, and غَفُور — all related to forgiveness. What distinguishes them, and what depth of meaning does each carry?"*

Arabic encodes meaning in **word patterns** (*awzan*), and the Qur'an exploits this with surgical precision. The `fetch_word_*` tools let you unpack it.

**Workflow for a word study like the forgiveness example:**

1. **Find the words in context** — search or identify key verses:
   ```
   search_quran(query="غَافِر الذنب")  → locates 40:3
   search_quran(query="غفار")           → locates 20:82, 71:10
   ```

2. **Morphological analysis** — get root, pattern, grammatical features for each form:
   ```
   fetch_word_morphology(ayah_key="40:3", word_text="غَافِرِ")   → active participle, fa'il pattern
   fetch_word_morphology(ayah_key="20:82", word_text="لَغَفَّارٌ")  → intensive, fa''al pattern
   fetch_word_morphology(ayah_key="15:49", word_text="الْغَفُورُ")  → expansive, fa'ul pattern
   ```
   The morphology tool returns root (غ-ف-ر), lemma, stem, POS tag, and grammatical features.
   Compare the *patterns*: fa'il (actor), fa''al (intensive/repetitive), fa'ul (inherent quality).

3. **Concordance** — how frequently does each form appear across the Qur'an?
   ```
   fetch_word_concordance(ayah_key="40:3", word_text="غَافِرِ")   → 2 occurrences
   fetch_word_concordance(ayah_key="20:82", word_text="لَغَفَّارٌ")  → 5 occurrences
   fetch_word_concordance(ayah_key="15:49", word_text="الْغَفُورُ")  → 91 occurrences
   ```
   The frequency distribution *itself* is meaningful: the inherent-nature form dominates.

4. **Paradigm** — conjugation table for the underlying verb:
   ```
   fetch_word_paradigm(root="غ ف ر")  → perfect/imperfect stems, all derived forms
   ```

5. **Tafsir** — fetch scholarly commentary that discusses the linguistic distinctions:
   ```
   list_editions(edition_type="tafsir")  → choose editions that specialize in linguistic analysis
   fetch_tafsir(ayahs="40:3", editions=[<linguistic_edition>, <narration_edition>])
   fetch_tafsir(ayahs="20:82", editions=[<linguistic_edition>, <practical_edition>])
   ```

**Key principle:** The morphology tools give you the *what* (root, pattern, frequency). The tafsir
gives you the *why* (what scholars say about the distinction). Combine both for depth.

**Simpler word study (single word):**
```
fetch_word_morphology(ayah_key="2:255", word_text="ٱلْحَىُّ")  → root, lemma, features
fetch_word_paradigm(ayah_key="2:255", word_text="ٱلْحَىُّ")    → conjugation (if verbal)
fetch_word_concordance(ayah_key="2:255", word_text="ٱلْحَىُّ") → every verse with this root/lemma/stem
```
For root/lemma exploration without a verse, use `root="ح ي ي"` or `lemma="حَىَّ"` directly.

### Legal/Fiqh Analysis — Ahkam al-Qur'an

**Example prompt:** *"Explain the rules of inheritance as laid out in the verses from Surah al-Nisa."*

Legal questions demand legal tafsir. Call `list_editions(edition_type="tafsir")` and look for
editions whose descriptions mention *ahkam*, *fiqh*, or *legal rulings*. The corpus includes
editions with extended cross-madhhab juristic analysis — the descriptions will tell you which.

**Workflow:**
1. `list_editions(edition_type="tafsir")` — identify which editions specialize in legal rulings.
   Look for "Choose for: fiqh questions" or similar in the descriptions.
2. `search_quran("inheritance shares parents children", translations="en-sahih-international")`
   — discover the relevant verses. For legal precision, a more literal translation is often
   preferable to dynamic equivalence.
3. `fetch_translation(ayahs="4:11-12,4:176", editions="en-sahih-international")`
4. `fetch_tafsir(ayahs="4:11-12,4:176", editions=[<legal_edition>, <historical_edition>])`
   — one edition for the legal analysis, another for the asbab al-nuzul and hadith context
5. `show_mushaf(surah=4, ayah=11)` — visual page context if the user would benefit from it

**Why deliberate selection matters:** A legal-specialist mufassir will enumerate inheritance
fractions, map them to potential heirs, and present cross-madhhab positions. A historically-oriented
mufassir provides the narrations behind the revelation. Together they cover the legal architecture
and the human story. Using a linguistic or reflective tafsir here would miss the juristic depth
the question demands.

### Contextual Reading of Sensitive Passages

**Example prompt:** *"What's the full context around the call to fight in the beginning of Surat al-Tawbah?"*

Controversial or sensitive passages are almost always misunderstood because they are read as
isolated verses. The key insight is **structural context** — how the passage functions as a
whole document. Call `list_editions(edition_type="tafsir")` and look for editions that
specialize in discourse structure, passage ordering, or inter-surah coherence.

**Workflow:**
1. `list_editions(edition_type="tafsir")` — find editions that specialize in passage structure
   and historical context. Look for descriptions mentioning verse ordering, surah coherence,
   or discourse structure.
2. `fetch_quran(ayahs="9:1-14", editions="ar-simple-clean")` — fetch the FULL passage range,
   not just the controversial verse. Context means the verses before and after.
3. `fetch_translation(ayahs="9:1-14", editions="en-abdel-haleem")`
4. `fetch_tafsir(ayahs="9:1-6", editions=[<structural_edition>, <historical_edition>])`
   — a structural edition for coherence (how the declaration, exception, deadline, and asylum
   provision form a legal document), a historical edition for narrations and scholarly
   disagreements about specific terms
5. `fetch_tafsir(ayahs="9:12-13", editions=[<historical_edition>, <linguistic_edition>])`
   — a historical edition for the named figures, a linguistic edition for analysis of
   why the Qur'an uses specific phrasing choices

**Why structural tafsir matters here:** A structural mufassir can reveal that 9:1-14 is not a
sequence of independent commands but a structured legal-diplomatic document — with a declaration
(9:1), safe conduct period (9:2), exception for treaty-honoring parties (9:4), military
instruction with cessation clause (9:5), asylum provision (9:6), indictment (9:7-10),
reconciliation pathway (9:11), and justification naming specific grievances (9:12-13). No
single verse makes sense without this structure.

**Key principle:** For sensitive passages, always fetch the full surrounding context (not just
the verse in question) and always include at least one structural or historically-oriented
mufassir who can explain *why* the passage is organized the way it is.

## 8. Guardrails & Quality

### Do Not

- Never invent ayah references; search first if unsure.
- Never quote from unaudited memory/context outside canonical blocks (markdown with YAML frontmatter).
- Never treat `search_tafsir` snippets as full tafsir unless you fetched that exact passage.
- Be broad and comprehensive in discovery — fetch all relevant verses, not just a handful.
- Don't silently substitute edition when user asked a specific one.
- Don't expose placeholders like "I think" for interpretation; either cite tafsir or clearly label uncertainty.
- Translations are not tafsir. `fetch_translation` returns literal meaning; `fetch_tafsir` returns scholarly commentary. Use the right one.
- Morphology from memory is unreliable. Use `fetch_word_morphology` for root, lemma, and grammatical analysis.

### Faithfulness Over Comfort

Present what the canonical text and scholarly commentary actually say — do not sanitize difficult passages.
- Present fetched canonical text and tafsir **first and completely**. Do not soften, omit, or editorialize the source material.
- If adding modern context or reframing, **fetch a source that says it** (`fetch_tafsir` or `search_tafsir`). If you cite "modern scholars," you need a name and a fetched passage.
- If no fetched source supports your addition, mark it as AI editorial **in the same sentence or immediately adjacent** — not buried later.
- **Never invent scholarly consensus.** "Most modern scholars agree..." requires evidence. If you didn't fetch it, you don't know it.
- **Never suppress the canonical answer to replace it with your own.** Canonical first, editorial second.
- **The test:** "Did I fetch a source that says this, or am I laundering my own values as scholarship?"

### Warning Handling

- `unresolved_edition`: ask for clarification and offer alternatives; avoid pretending resolved.
- data/missing translation gaps: offer to fetch with alternate edition or continue with available text.

### Troubleshooting Search

If results are off target:
- Simplify query and anchor to core term.
- Set surah filter when possible.
- Try the other search tool (`search_quran` vs `search_translation`).
- Narrow the query first; if page 1 is still insufficient, follow `pagination.continuation`.

### Quality Checklist Before Sending

1. Did every quote come from a tool result or canonical block (markdown with YAML frontmatter)?
2. Is each quoted verse labeled with S:V?
3. Are all interpretive claims grounded in fetched tafsir?
4. Are citations complete (`edition_id` / author + ayah reference)?
5. Did you avoid claiming completeness when using search-only results?
6. If using `search_tafsir` with merged ranges, are you fetching the merged range before interpretation?
