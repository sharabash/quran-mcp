"""Arabic text normalization for morphological matching.

Normalizes Arabic input so it can be matched against the dict_root,
dict_lemma, and dict_stem tables which store cleaned forms.
"""

import re
import unicodedata

# Unicode ranges for Arabic diacritics (tashkeel)
_DIACRITICS = re.compile(
    "["
    "\u0610-\u061A"  # Small marks above/below
    "\u064B-\u065F"  # Fathatan through Waslah
    "\u0670"          # Superscript alef
    "\u06D6-\u06DC"  # Small high ligatures
    "\u06DF-\u06E4"  # Small high signs
    "\u06E7-\u06E8"  # Small high/low
    "\u06EA-\u06ED"  # Small low
    "\u08D3-\u08E1"  # Extended Arabic marks
    "\u08E3-\u08FF"  # Extended Arabic marks
    "\uFE70-\uFE7F"  # Presentation forms (tanween etc.)
    "]"
)

# Tatweel / kashida
_TATWEEL = "\u0640"

# Alif variants → bare alif
_ALIF_VARIANTS = str.maketrans({
    "\u0623": "\u0627",  # أ (alif with hamza above) → ا
    "\u0625": "\u0627",  # إ (alif with hamza below) → ا
    "\u0622": "\u0627",  # آ (alif with madda) → ا
    "\u0671": "\u0627",  # ٱ (alif wasla) → ا
})

# Alif maqsura → ya
_ALIF_MAQSURA = str.maketrans({
    "\u0649": "\u064A",  # ى → ي
})

# Ta marbuta → ha (for matching only)
_TA_MARBUTA = str.maketrans({
    "\u0629": "\u0647",  # ة → ه
})


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for matching against dictionary tables.

    Steps:
    1. Unicode NFC normalization
    2. Strip tatweel/kashida (U+0640)
    3. Strip all diacritics (tashkeel)
    4. Alif variants: أ إ آ ٱ → ا
    5. Alif maqsura: ى → ي
    6. Ta marbuta: ة → ه
    """
    # NFC normalization first
    text = unicodedata.normalize("NFC", text)
    # Strip tatweel
    text = text.replace(_TATWEEL, "")
    # Strip diacritics
    text = _DIACRITICS.sub("", text)
    # Normalize alif variants
    text = text.translate(_ALIF_VARIANTS)
    # Alif maqsura → ya
    text = text.translate(_ALIF_MAQSURA)
    # Ta marbuta → ha
    text = text.translate(_TA_MARBUTA)
    return text.strip()
