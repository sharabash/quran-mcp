# Usage Example Exports

Quran Markdown (`.qmd`) files exported by the `quran-mcp-new-usage-example` skill.

Each file is a rich, grounded Quran scholarship response in structured markdown
with `:::directive` blocks that map to the documentation app's CSS classes
(`.vb`, `.sq`, `.insight`, `.commentary`, `.grounding`, etc.).

## Workflow

1. User asks a Quran question via Claude Code with the `quran-mcp-new-usage-example` skill
2. Claude responds using quran-mcp tools (grounded, multi-source)
3. User reviews the terminal output and approves
4. Claude exports to `<slug>.qmd` in this directory

## Format

See `.skills/quran-mcp-new-usage-example/references/export-format.md`
for the complete Quran Markdown specification.

## Publishing to /documentation

To show a QMD file on the documentation page, add its filename to `manifest.json`
in this directory. The manifest is a JSON array — order controls display order.

```json
[
  "sealing-of-hearts-five-scholars-study.qmd",
  "another-example.qmd"
]
```

At build time, `src/quran_mcp/lib/qmd_parser.py` reads the manifest, parses each
listed QMD file into HTML, and feeds the result into the Svelte documentation app
alongside any static (hand-crafted Jinja2) showcases registered in
`src/quran_mcp/lib/documentation_site.py`.

Not every QMD file in this directory needs to be in the manifest — unlisted files
are simply stored here as archives or drafts.
