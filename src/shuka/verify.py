import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shuka.config import settings


@dataclass
class Cue:
    surface: str
    anchor: str
    start: int = 0


@dataclass
class NumberCue:
    surface: str
    value: float
    anchor: str
    start: int = 0


@dataclass
class Cues:
    negations: list[Cue] = field(default_factory=list)
    lateralities: list[Cue] = field(default_factory=list)
    numbers: list[NumberCue] = field(default_factory=list)


@dataclass
class VerificationReport:
    flags: list = field(default_factory=list)
    verified: bool = True


def _load_lexicon(name: str) -> dict:
    return json.loads((settings.lexicon_dir / name).read_text())


_negation = _load_lexicon("negation.json")
_laterality = _load_lexicon("laterality.json")
_quantities = _load_lexicon("quantities.json")

_STOPWORDS = {"mein", "hai", "tha", "ki", "se", "ke", "ka", "ko", "aur", "ya",
              "in", "the", "a", "an", "and", "or", "of", "to", "for", "with"}


def _lang_key(lang: str) -> str:
    return lang.split("-")[0].lower()


def _tokenize(text: str) -> list[tuple[str, int]]:
    """Returns list of (token, start_pos). Keeps hyphenated tokens whole."""
    tokens = []
    for m in re.finditer(r'[\wऀ-ॿ஀-௿][\wऀ-ॿ஀-௿-]*', text):
        tokens.append((m.group().lower(), m.start()))
    return tokens


def _nearest_anchor(tokens: list[tuple[str, int]], pos: int, window: int = 2) -> str:
    """Find nearest non-stopword token within window positions, preceding preferred."""
    idx = next((i for i, (t, p) in enumerate(tokens) if p >= pos), len(tokens))
    candidates = []
    for offset in range(1, window + 2):
        if idx - offset >= 0:
            tok, _ = tokens[idx - offset]
            if tok not in _STOPWORDS and len(tok) > 2:
                candidates.append(tok)
                break
    if not candidates:
        for offset in range(1, window + 2):
            if idx + offset < len(tokens):
                tok, _ = tokens[idx + offset]
                if tok not in _STOPWORDS and len(tok) > 2:
                    candidates.append(tok)
                    break
    return candidates[0] if candidates else ""


def normalize_quantity(text: str) -> Optional[float]:
    """Normalize a quantity expression to a float. Returns None if unrecognized."""
    text = text.strip().lower()
    coll = _quantities["colloquial"]
    if text in coll:
        return coll[text]
    # paune X = value(X) - 0.25
    for pw in _quantities["paune_words"]:
        if text.startswith(pw + " "):
            rest = text[len(pw):].strip()
            v = normalize_quantity(rest)
            if v is not None:
                return v - 0.25
    # sava X = value(X) + 0.25
    if text.startswith("sava "):
        rest = text[5:].strip()
        v = normalize_quantity(rest)
        if v is not None:
            return v + 0.25
    # digit
    try:
        return float(text)
    except ValueError:
        pass
    # word maps
    for lang_words in _quantities["words"].values():
        if text in lang_words:
            return float(lang_words[text])
    return None


def _forward_anchor(tokens: list[tuple[str, int]], pos: int, window: int = 3) -> str:
    """Find nearest non-stopword token at or after pos (for unit anchors after numbers)."""
    idx = next((i for i, (t, p) in enumerate(tokens) if p >= pos), len(tokens))
    for offset in range(0, window + 1):
        if idx + offset < len(tokens):
            tok, _ = tokens[idx + offset]
            if tok not in _STOPWORDS and len(tok) > 2:
                return tok
    return ""


def _find_echo_anchor(low: str, neg_start: int) -> Optional[str]:
    """Look backwards from neg_start for a hyphenated echo-form token like 'bukhar-vukhar'."""
    # Search in the text before the negation marker for a hyphenated word
    text_before = low[:neg_start]
    # Find the last hyphenated token in the text before the negation
    m = None
    for candidate in re.finditer(r'[\wऀ-ॿ஀-௿][\wऀ-ॿ஀-௿]*-[\wऀ-ॿ஀-௿]+', text_before):
        m = candidate
    if m:
        return m.group()
    return None


def detect_cues(text: str, lang: str) -> Cues:
    lk = _lang_key(lang)
    tokens = _tokenize(text)
    low = text.lower()
    cues = Cues()

    # negations
    neg_list = _negation.get(lk, []) + (_negation.get("en", []) if lk != "en" else [])
    for marker in neg_list:
        for m in re.finditer(re.escape(marker), low):
            anchor = _nearest_anchor(tokens, m.start())
            # For echo forms like "bukhar-vukhar", find the hyphenated token before negation
            echo_anchor = _find_echo_anchor(low, m.start())
            if echo_anchor:
                anchor = echo_anchor
            cues.negations.append(Cue(surface=marker, anchor=anchor, start=m.start()))

    # lateralities
    lat_list = _laterality.get(lk, []) + (_laterality.get("en", []) if lk != "en" else [])
    for marker in lat_list:
        for m in re.finditer(r'\b' + re.escape(marker) + r'\b', low):
            anchor = _nearest_anchor(tokens, m.start())
            cues.lateralities.append(Cue(surface=marker, anchor=anchor, start=m.start()))

    # numbers — colloquial + word + digit
    all_qty = {}
    all_qty.update(_quantities["colloquial"])
    for wmap in _quantities["words"].values():
        all_qty.update(wmap)
    # add paune compounds
    for pw in _quantities["paune_words"]:
        for base_word, base_val in list(all_qty.items()):
            compound = f"{pw} {base_word}"
            all_qty[compound] = base_val - 0.25

    # sort by length desc to match longer tokens first
    for qty_str in sorted(all_qty, key=len, reverse=True):
        for m in re.finditer(r'\b' + re.escape(qty_str) + r'\b', low):
            val = normalize_quantity(qty_str)
            if val is None:
                continue
            anchor = _forward_anchor(tokens, m.end())
            # find a unit near this number
            unit_found = any(u in low[m.start():m.start() + 40] for u in _quantities["units"])
            if unit_found:
                cues.numbers.append(NumberCue(surface=qty_str, value=val,
                                               anchor=anchor, start=m.start()))

    # also catch bare digits with units
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\b', low):
        val = float(m.group(1))
        unit_found = any(u in low[m.start():m.start() + 40] for u in _quantities["units"])
        if unit_found:
            anchor = _forward_anchor(tokens, m.end())
            cues.numbers.append(NumberCue(surface=m.group(1), value=val,
                                           anchor=anchor, start=m.start()))

    return cues


# ── TASK 7: VerificationReport + cross_check ──────────────────────────────

from shuka.schema import DriftKind, VerificationFlag


_SIDE_MAP = {
    "baayan": "left", "baayein": "left", "left": "left", "idadu": "left",
    "daayan": "right", "daayein": "right", "right": "right", "valadu": "right",
    "bilateral": "both", "dono taraf": "both", "irandu pakkam": "both",
}


def cross_check(cues_orig, cues_en) -> VerificationReport:
    """Detect drift between the two ASR views. Bias toward flagging (recall > precision).
    cues_orig=None → fail SAFE: verified=False, all safety-critical facts need confirmation."""
    if cues_orig is None:
        return VerificationReport(flags=[], verified=False)

    flags = []

    # Negation: count mismatch — extra originals unflagged by EN are dropped negations
    for i, neg in enumerate(cues_orig.negations):
        matched = i < len(cues_en.negations)
        if not matched:
            flags.append(VerificationFlag(
                fact_ref=neg.anchor,
                kind=DriftKind.NEGATION,
                detail=f"negation '{neg.surface}' present in original, absent in EN translation",
                original_evidence=neg.surface,
            ))

    # Also flag EN negations with no original counterpart (spurious negation added by translation)
    for i, neg in enumerate(cues_en.negations):
        if i >= len(cues_orig.negations):
            flags.append(VerificationFlag(
                fact_ref=neg.anchor,
                kind=DriftKind.NEGATION,
                detail=f"negation '{neg.surface}' present in EN but absent in original",
                original_evidence=None,
            ))

    # Laterality: semantic side comparison
    for lat in cues_orig.lateralities:
        orig_side = _SIDE_MAP.get(lat.surface.lower())
        en_sides = [_SIDE_MAP.get(e.surface.lower()) for e in cues_en.lateralities]
        if orig_side and orig_side not in en_sides:
            flags.append(VerificationFlag(
                fact_ref=lat.anchor,
                kind=DriftKind.LATERALITY,
                detail=f"laterality '{lat.surface}' (={orig_side}) not found in EN translation",
                original_evidence=lat.surface,
            ))

    # Number: value drift (zero tolerance)
    for i, num in enumerate(cues_orig.numbers):
        if i < len(cues_en.numbers):
            en_val = cues_en.numbers[i].value
            if abs(num.value - en_val) > 0.01:
                flags.append(VerificationFlag(
                    fact_ref=num.anchor,
                    kind=DriftKind.NUMBER,
                    detail=f"number drifted: original={num.value} ({num.surface}), EN={en_val}",
                    original_evidence=num.surface,
                ))
        else:
            flags.append(VerificationFlag(
                fact_ref=num.anchor,
                kind=DriftKind.NUMBER,
                detail=f"number '{num.surface}'={num.value} in original dropped in EN",
                original_evidence=num.surface,
            ))

    return VerificationReport(flags=flags, verified=True)
