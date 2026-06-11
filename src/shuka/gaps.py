import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Lexicons:
    collapse_map: dict
    festivals: dict
    echo_onsets: dict
    event_verbs: dict
    register_tokens: dict
    phenomenology: dict
    symptom_names: list

    @classmethod
    def load(cls, d: Path) -> "Lexicons":
        def j(n):
            return json.loads((d / n).read_text())
        return cls(
            collapse_map=j("collapse_map.json"),
            festivals=j("festivals.json"),
            echo_onsets=j("echo_patterns.json"),
            event_verbs=j("event_verbs.json"),
            register_tokens=j("register_tokens.json"),
            phenomenology=j("phenomenology.json"),
            symptom_names=j("symptom_names.json"),
        )

    @property
    def phenomenology_whitelist(self) -> set:
        return {w for words in self.phenomenology.values() for w in words}

    def festival_date(self, name: str, year: int) -> datetime.date:
        key = self.festivals["aliases"].get(name.lower(), name.lower())
        return datetime.date.fromisoformat(self.festivals["events"][key][str(year)])


# ── Task 11: Three detectors ──────────────────────────────────────────────────

from shuka.schema import Gap, GapKind
from shuka.verify import detect_cues


def _lang_key(lang: str) -> str:
    return lang.split("-")[0].lower()


def detect_lexical_collapse(original: str, lang: str, lex: Lexicons) -> list:
    table = lex.collapse_map.get(_lang_key(lang), {})
    low = original.lower()
    out = []
    for term, entry in table.items():
        if re.search(rf"\b{re.escape(term)}\b", low):
            out.append(Gap(
                field=f"symptom:{term}",
                kind=GapKind.LEXICAL_COLLAPSE,
                reason=f"'{term}' spans {len(entry['referents'])} clinical referents",
                patient_term=term,
                followup_vernacular=entry["probe"],
                followup_options=list(entry["options"]),
            ))
    return out


ECHO = re.compile(r"\b([\wऀ-ॿ஀-௿]{3,})[- ]([\wऀ-ॿ஀-௿]{3,})\b")


def detect_category_denial(original: str, lang: str, lex: Lexicons) -> list:
    onsets = lex.echo_onsets.get(_lang_key(lang), [])
    negs = detect_cues(original, lang).negations
    out = []
    for m in ECHO.finditer(original.lower()):
        base, echo = m.group(1), m.group(2)
        is_echo = any(echo == o + base[1:] for o in onsets)
        if not is_echo:
            continue
        near_neg = any(abs(n.start - m.end()) < 30 for n in negs)
        if near_neg:
            pair = f"{base}-{echo}"
            out.append(Gap(
                field=f"symptom:{base}",
                kind=GapKind.CATEGORY_DENIAL,
                reason="echo reduplication denies a fuzzy category, not one symptom",
                patient_term=pair,
                followup_vernacular=f"{base.capitalize()} nahi tha — us jaisa kuch aur bhi nahi?",
                followup_options=["kuch nahi tha", "thoda kuch tha"],
            ))
    return out


def detect_frequency_drop(original: str, lang: str, lex: Lexicons) -> list:
    verbs = lex.event_verbs.get(_lang_key(lang), [])
    numbers = detect_cues(original, lang).numbers
    low = original.lower()
    out = []
    for verb in verbs:
        i = low.find(verb)
        if i < 0:
            continue
        counted = any(abs(n.start - i) < 35 for n in numbers)
        if not counted:
            out.append(Gap(
                field=f"event:{verb}",
                kind=GapKind.FREQUENCY_DROP,
                reason="pro-drop grammar omitted the count",
                patient_term=verb,
                followup_vernacular=f"Kitni baar {verb}?",
            ))
    return out


# ── Task 12: Temporal anchor resolver ─────────────────────────────────────────

TEMPORAL_MARKERS = ["ke baad", "se", "time la irundhu", "jab se", "kku aprum", "ke baad se"]


def detect_temporal_anchor(original: str, lang: str, lex: Lexicons,
                            encounter: datetime.date) -> list:
    low = original.lower()
    out = []
    known = set(lex.festivals["events"]) | set(lex.festivals["aliases"])
    for name in known:
        i = low.find(name)
        if i < 0:
            continue
        window = low[i:i + len(name) + 30]
        marker = next((mk for mk in sorted(TEMPORAL_MARKERS, key=len, reverse=True)
                       if mk in window), None)
        if marker is None:
            continue
        try:
            fdate = lex.festival_date(name, encounter.year)
        except KeyError:
            continue
        if fdate > encounter:
            try:
                fdate = lex.festival_date(name, encounter.year - 1)
            except KeyError:
                continue
        days = (encounter - fdate).days
        if days < 0:
            continue
        phrase = f"{name} {marker}".strip()
        weeks = round(days / 7)
        out.append(Gap(
            field="hpi.duration",
            kind=GapKind.TEMPORAL_ANCHOR,
            reason="duration anchored to regional calendar, not the clock",
            patient_term=phrase,
            resolution_candidate=f"~{days} days (anchor: '{phrase}')",
            followup_vernacular=(
                f"{name.capitalize()} {marker} matlab, lagbhag "
                f"{weeks} hafte? Theek se yaad hai ya andaaza?"
            ),
            followup_options=["theek se yaad hai", "andaaza hai"],
        ))
    return out


# ── Task 13: Register-switch + HPI dimension gaps ─────────────────────────────

from shuka.schema import HPI, IntakeNote

HPI_PROBES = {
    "onset": "Yeh kab shuru hua?",
    "duration": "Kitne din se hai?",
    "character": "Dard kaisa hai — jalan jaisa, marod jaisa, sui chubhne jaisa, ya bhaari-bhaari?",
    "location": "Kahan par hota hai?",
}


def detect_register_switch(original: str, lang: str, lex: Lexicons) -> list:
    low = original.lower()
    out = []
    for tok in lex.register_tokens["biomedical_english"]:
        if re.search(rf"\b{re.escape(tok)}\b", low):
            out.append(Gap(
                field=f"history:{tok}",
                kind=GapKind.REGISTER_AMBIG,
                reason="English biomedical token in vernacular matrix — likely doctor-told",
                patient_term=tok,
                followup_vernacular=(
                    f"{tok.upper() if len(tok) <= 3 else tok.capitalize()}"
                    " — doctor ne bataya tha, ya aapko khud aisa lagta hai?"
                ),
                followup_options=["doctor ne bataya tha", "khud mehsoos hota hai"],
            ))
    lk = _lang_key(lang)
    for idiom in lex.register_tokens["somatic_idioms"].get(lk, []):
        if idiom in low:
            out.append(Gap(
                field=f"symptom:{idiom}",
                kind=GapKind.REGISTER_AMBIG,
                reason="somatic idiom; may be experiential or affective — elicit, don't label",
                patient_term=idiom,
                followup_vernacular=f"'{idiom}' — thoda aur bataiye, kaisa mehsoos hota hai?",
            ))
    return out


def detect_hpi_dimension(note: IntakeNote) -> list:
    out = []
    for f, probe in HPI_PROBES.items():
        if getattr(note.hpi, f) is None:
            out.append(Gap(
                field=f"hpi.{f}",
                kind=GapKind.HPI_DIMENSION,
                followup_vernacular=probe,
                followup_options=(
                    ["jalan jaisa", "marod jaisa", "sui chubhne jaisa", "bhaari-bhaari"]
                    if f == "character" else []
                ),
            ))
    return out
