/**
 * Word-level selection store for mushaf phrase interaction.
 *
 * Selection is contiguous within a single ayah. The store tracks which
 * ayah is active and which word positions are selected. Each VerseLine
 * component reads from this store to compute its own highlight segments.
 */

import { writable, get } from "svelte/store";

export interface WordSelection {
  /** Surah number of the selected ayah */
  surah: number;
  /** Ayah number within the surah */
  ayah: number;
  /** verse_key string, e.g. "2:186" */
  verseKey: string;
  /** Set of word positions (position_in_verse) that are selected */
  words: Set<number>;
}

/** The current word selection, or null if nothing is selected. */
export const wordSelection = writable<WordSelection | null>(null);

/** Toggle a word in the selection. If the word is in a different ayah,
 *  start a new selection. If the word is already selected, deselect it.
 *  If deselecting the last word, clear the selection entirely. */
export function toggleWord(
  surah: number,
  ayah: number,
  verseKey: string,
  wordPosition: number,
): void {
  const current = get(wordSelection);

  // Different ayah → start fresh
  if (!current || current.verseKey !== verseKey) {
    wordSelection.set({
      surah,
      ayah,
      verseKey,
      words: new Set([wordPosition]),
    });
    return;
  }

  // Same ayah — toggle the word
  const next = new Set(current.words);
  if (next.has(wordPosition)) {
    // Truncate: remove this word and all words after it in reading order.
    // Maintains phrase contiguity — deselecting a middle word keeps only
    // the earlier portion of the phrase.
    for (const p of [...next]) {
      if (p >= wordPosition) next.delete(p);
    }
  } else {
    next.add(wordPosition);
  }

  // If no words left, clear selection
  if (next.size === 0) {
    wordSelection.set(null);
    return;
  }

  wordSelection.set({ ...current, words: next });
}

/** Clear the selection entirely. */
export function clearSelection(): void {
  wordSelection.set(null);
}

// ─── Drag-to-select state ───────────────────────────────

/** Anchor word for drag-to-select. Set on pointerdown, cleared on pointerup. */
let dragAnchor: {
  surah: number;
  ayah: number;
  verseKey: string;
  position: number;
} | null = null;

/** Track whether the pointer moved to a different word during drag. */
let didDrag = false;
/** Track whether the tapped word was already selected before startDrag. */
let initiallySelected = false;
/** One-shot flag: suppress the next click-dismiss after a real drag.
 *  Set in endDrag when didDrag is true, consumed by handleDismiss. */
let suppressNextClickDismiss = false;

/** Begin a drag selection. Called on pointerdown on a word.
 *  Sets dragAnchor for drag tracking. Applies selection immediately
 *  (extends if adjacent, replaces if not). Records whether the word
 *  was already selected for tap-to-deselect detection in endDrag. */
export function startDrag(
  surah: number,
  ayah: number,
  verseKey: string,
  wordPosition: number,
): void {
  const current = get(wordSelection);
  initiallySelected = !!(
    current &&
    current.verseKey === verseKey &&
    current.words.has(wordPosition)
  );
  didDrag = false;
  dragAnchor = { surah, ayah, verseKey, position: wordPosition };
  applyTapSelection(surah, ayah, verseKey, wordPosition);
}

/** Shared logic for tap/drag start: extend if adjacent, replace if not. */
function applyTapSelection(
  surah: number,
  ayah: number,
  verseKey: string,
  wordPosition: number,
): void {
  const current = get(wordSelection);
  if (current && current.verseKey === verseKey) {
    // Same ayah — check if adjacent to existing selection
    const sorted = [...current.words].sort((a, b) => a - b);
    const min = sorted[0];
    const max = sorted[sorted.length - 1];
    if (wordPosition === min - 1 || wordPosition === max + 1) {
      const next = new Set(current.words);
      next.add(wordPosition);
      wordSelection.set({ ...current, words: next });
      return;
    }
    // Already selected — keep as-is
    if (current.words.has(wordPosition)) {
      return;
    }
  }

  // Different ayah or non-adjacent — start fresh
  wordSelection.set({
    surah,
    ayah,
    verseKey,
    words: new Set([wordPosition]),
  });
}

/** Extend drag selection to include all words between anchor and current.
 *  Called on pointerenter over a word during drag.
 *  validPositions: actual word positions in this verse (filters out end markers). */
export function extendDrag(
  verseKey: string,
  wordPosition: number,
  validPositions?: number[],
): void {
  if (!dragAnchor || dragAnchor.verseKey !== verseKey) return;
  didDrag = true;
  const min = Math.min(dragAnchor.position, wordPosition);
  const max = Math.max(dragAnchor.position, wordPosition);
  const words = new Set<number>();
  if (validPositions) {
    for (const p of validPositions) {
      if (p >= min && p <= max) words.add(p);
    }
  } else {
    for (let i = min; i <= max; i++) words.add(i);
  }
  wordSelection.set({
    surah: dragAnchor.surah,
    ayah: dragAnchor.ayah,
    verseKey: dragAnchor.verseKey,
    words,
  });
}

/** Finalize drag selection. Called on pointerup.
 *  If no drag occurred and the tapped word was already selected,
 *  toggle it off (tap-to-deselect). */
export function endDrag(): void {
  if (dragAnchor && !didDrag && initiallySelected) {
    // Tap on an already-selected word → deselect it
    toggleWord(
      dragAnchor.surah,
      dragAnchor.ayah,
      dragAnchor.verseKey,
      dragAnchor.position,
    );
  }
  if (didDrag) suppressNextClickDismiss = true;
  dragAnchor = null;
  didDrag = false;
  initiallySelected = false;
}

/** Consume (and clear) the one-shot click-dismiss suppression flag.
 *  Returns true if a drag just completed and the next dismiss should be skipped. */
export function consumeClickDismissSuppression(): boolean {
  const v = suppressNextClickDismiss;
  suppressNextClickDismiss = false;
  return v;
}

/** Whether a drag is currently in progress. */
export function isDragging(): boolean {
  return dragAnchor !== null;
}

// ─── Segment computation ────────────────────────────────

export type SegmentPosition = "only" | "start" | "middle" | "end";

/** For a given word position in a line, determine its segment role
 *  within the selection ranges that intersect this line's words.
 *  Returns null if the word is not selected. */
export function getSegmentPosition(
  wordPosition: number,
  selectedPositions: Set<number>,
  lineWordPositions: number[],
): SegmentPosition | null {
  if (!selectedPositions.has(wordPosition)) return null;

  const selectedOnLine = lineWordPositions.filter((p) =>
    selectedPositions.has(p),
  );
  if (selectedOnLine.length === 0) return null;

  const min = Math.min(...selectedOnLine);
  const max = Math.max(...selectedOnLine);

  if (min === max) return "only";
  if (wordPosition === min) return "start";
  if (wordPosition === max) return "end";
  return "middle";
}
