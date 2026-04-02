/**
 * TypeScript types mirroring Python dataclasses from quran_mcp.lib.mushaf.types.
 *
 * These types represent the structured_content returned by show_mushaf
 * and fetch_mushaf tools (serialized via dataclasses.asdict).
 */

export interface MushafWord {
  word_id: number;
  verse_id: number;
  text: string;
  /** "word", "end", "pause_mark", etc. */
  char_type_name: string;
  line_number: number;
  position_in_line: number;
  position_in_verse: number;
  /** QCF V2 PUA glyph text (may include embedded pause mark), null if unavailable */
  glyph_text: string | null;
}

export interface PageLine {
  line_number: number;
  words: MushafWord[];
}

export interface PageVerse {
  verse_id: number;
  /** e.g. "2:255" */
  verse_key: string;
  chapter_id: number;
  verse_number: number;
}

export interface SurahHeader {
  chapter_id: number;
  name_arabic: string;
  name_simple: string;
  bismillah_pre: boolean;
  /** Render header above this line number */
  appears_before_line: number;
}

/** Server-detected client identity (injected at tool result time, not part of PageData dataclass). */
export interface ClientHint {
  host: "chatgpt" | "claude" | "unknown";
  platform: "mobile" | "desktop" | "unknown";
}

export interface PageData {
  page_number: number;
  mushaf_edition_id: number;
  total_pages: number;
  lines: PageLine[];
  verses: PageVerse[];
  surah_headers: SurahHeader[];
  /** chapter_id (stringified) → chapter name */
  chapter_names: Record<string, string>;
  /** Auto-select this verse on initial load (e.g. "2:255"), null if none */
  initial_selected_verse: string | null;
  /** Server-detected host and platform (injected by show_mushaf / fetch_mushaf). */
  client_hint?: ClientHint;
  /** Enable word selection and interaction UI. Default true. */
  interactive?: boolean;
  /** Optional grounding tax payload injected by middleware before acknowledgment. */
  grounding_rules?: string | null;
  /** Optional grounding warning injected by middleware before acknowledgment. */
  warnings?: Array<{ type: string; message?: string }>;
}
