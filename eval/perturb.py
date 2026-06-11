"""eval/perturb.py — Perturbation generators for OPD intake evaluation.

Each generator takes a raw transcript string and returns a list of (perturbed_str, label) tuples.
All perturbations are deterministic — no randomness.
"""
from __future__ import annotations
import re


def negate_symptom(transcript: str, symptom: str) -> list[tuple[str, str]]:
    """Inject a negation before the symptom token. Returns [(perturbed, label)]."""
    low = transcript.lower()
    idx = low.find(symptom.lower())
    if idx < 0:
        return []
    negated = transcript[:idx] + "nahi " + transcript[idx:]
    return [(negated, f"neg:{symptom}")]


def flip_laterality(transcript: str) -> list[tuple[str, str]]:
    """Flip left↔right, baayan↔daayan."""
    pairs = [
        ("left", "right"), ("right", "left"),
        ("baayan", "daayan"), ("daayan", "baayan"),
        ("idadu", "valadu"), ("valadu", "idadu"),
    ]
    results = []
    for src, dst in pairs:
        if re.search(rf"\b{re.escape(src)}\b", transcript, re.IGNORECASE):
            flipped = re.sub(rf"\b{re.escape(src)}\b", dst, transcript, flags=re.IGNORECASE)
            results.append((flipped, f"flip_lat:{src}→{dst}"))
    return results


def shift_duration(transcript: str) -> list[tuple[str, str]]:
    """Replace numeric duration tokens with different values.
    E.g. 'two days' → 'five days', 'teen din' → 'saat din'."""
    swaps = [
        (r"\btwo\b", "five"), (r"\bthree\b", "seven"), (r"\bone\b", "four"),
        (r"\bdo\b", "paanch"), (r"\bteen\b", "saat"), (r"\bek\b", "chaar"),
        (r"\brendu\b", "aindhu"), (r"\bmoonu\b", "ezhu"),
    ]
    results = []
    for pattern, replacement in swaps:
        if re.search(pattern, transcript, re.IGNORECASE):
            shifted = re.sub(pattern, replacement, transcript, flags=re.IGNORECASE)
            results.append((shifted, f"shift_dur:{pattern}→{replacement}"))
    return results


def drop_medication(transcript: str, med_term: str) -> list[tuple[str, str]]:
    """Remove a medication mention entirely."""
    idx = transcript.lower().find(med_term.lower())
    if idx < 0:
        return []
    end = idx + len(med_term)
    dropped = (transcript[:idx] + transcript[end:]).replace("  ", " ").strip()
    return [(dropped, f"drop_med:{med_term}")]


def add_category_denial(transcript: str, base_term: str, lang: str = "hi") -> list[tuple[str, str]]:
    """Inject echo-reduplication denial: 'bukhar' → 'bukhar-vukhar nahi'."""
    if lang == "hi":
        onset = "v"
        echo = onset + base_term[1:] if len(base_term) > 1 else base_term
        negation = "nahi"
    elif lang == "ta":
        onset = "ki"
        echo = onset + base_term[1:] if len(base_term) > 1 else base_term
        negation = "illai"
    else:
        return []
    idx = transcript.lower().find(base_term.lower())
    if idx < 0:
        return []
    insertion = f"{base_term}-{echo} {negation} "
    injected = transcript[:idx] + insertion + transcript[idx + len(base_term):]
    return [(injected, f"cat_denial:{base_term}-{echo}")]


# ── Convenience: apply all perturbations to one transcript ───────────────

def all_perturbations(
    transcript: str,
    *,
    lang: str = "hi",
    symptom: str = "fever",
    med_term: str = "tablet",
    base_term: str = "bukhar",
) -> list[tuple[str, str]]:
    """Apply all 5 perturbation types and return unique (text, label) pairs."""
    results: list[tuple[str, str]] = []
    results.extend(negate_symptom(transcript, symptom))
    results.extend(flip_laterality(transcript))
    results.extend(shift_duration(transcript))
    results.extend(drop_medication(transcript, med_term))
    results.extend(add_category_denial(transcript, base_term, lang))
    # Deduplicate by text
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for text, label in results:
        if text not in seen:
            seen.add(text)
            unique.append((text, label))
    return unique
