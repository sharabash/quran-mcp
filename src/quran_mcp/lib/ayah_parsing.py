"""Shared utilities for ayah key parsing and range handling."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def normalize_ayah_key(ayah_key: str | None = None, ayah: str | None = None) -> str:
    """Return the canonical ayah key while preserving the legacy alias."""
    if ayah_key is not None and ayah is not None and ayah_key != ayah:
        raise ValueError(f"Conflicting ayah values: {ayah_key!r} != {ayah!r}")
    return ayah_key or ayah or ""


def parse_ayah_key(ayah_key: str) -> tuple[int, int]:
    """Parse ``SURAH:AYAH`` into integers."""
    try:
        parts = ayah_key.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid ayah_key format '{ayah_key}', expected 'SURAH:AYAH'")
        surah = int(parts[0])
        ayah = int(parts[1])
        return surah, ayah
    except (ValueError, IndexError) as e:
        raise ValueError(f"Failed to parse ayah_key '{ayah_key}': {e}") from e


def parse_ayah_input(ayah_input: str | list[str]) -> list[str]:
    """Expand ayah keys and ranges into a flat list of ayah keys."""
    if isinstance(ayah_input, str):
        raw = ayah_input.strip()
        tokens = [t for t in re.split(r"[\s,]+", raw) if t]
    else:
        tokens = list(ayah_input)

    result: list[str] = []
    for item in tokens:
        if "-" in item and ":" in item:
            surah_part, verse_part = item.split(":")
            surah = int(surah_part)
            start_verse, end_verse = map(int, verse_part.split("-"))
            if end_verse < start_verse:
                start_verse, end_verse = end_verse, start_verse
            result.extend([f"{surah}:{v}" for v in range(start_verse, end_verse + 1)])
        else:
            result.append(item)
    return result


def format_ayah_range(ayah_keys: list[str]) -> str:
    """Format ayah keys into compact ranges."""
    if not ayah_keys:
        return ""
    if len(ayah_keys) == 1:
        return ayah_keys[0]

    parsed: list[tuple[int, int]] = []
    for key in ayah_keys:
        try:
            s, a = parse_ayah_key(key)
            parsed.append((s, a))
        except ValueError:
            logger.debug("Skipping unparseable ayah key: %s", key, exc_info=True)
            continue
    if not parsed:
        return ayah_keys[0]

    parsed.sort()

    ranges: list[str] = []
    run_start = parsed[0]
    run_end = parsed[0]

    for i in range(1, len(parsed)):
        s, a = parsed[i]
        if s == run_end[0] and a == run_end[1] + 1:
            run_end = (s, a)
        else:
            if run_start == run_end:
                ranges.append(f"{run_start[0]}:{run_start[1]}")
            else:
                ranges.append(f"{run_start[0]}:{run_start[1]}-{run_end[1]}")
            run_start = (s, a)
            run_end = (s, a)

    if run_start == run_end:
        ranges.append(f"{run_start[0]}:{run_start[1]}")
    else:
        ranges.append(f"{run_start[0]}:{run_start[1]}-{run_end[1]}")

    return ", ".join(ranges)
