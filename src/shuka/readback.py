"""Build 4-part read-back summary and synthesize audio via Bulbul TTS."""
from __future__ import annotations

from shuka.config import settings
from shuka.sarvam import SarvamClient
from shuka.schema import DriftKind, FactStatus, GapKind, IntakeNote

_client = SarvamClient(settings)

# ── Part templates ────────────────────────────────────────────────────────

def _part1_complaint(note: IntakeNote, lang: str) -> str:
    """Part 1: Chief complaint + duration."""
    words = note.chief_complaint_patient_words or note.chief_complaint
    duration = (note.hpi.duration or "").strip()
    if "hi" in lang:
        if duration:
            return f"Aapne bataya ki aapko {words} hai, jo {duration} se hai."
        return f"Aapne bataya ki aapko {words} hai."
    elif "ta" in lang:
        if duration:
            return f"Neenga {words} irukkudhu, {duration} aagudhu endru sollineenga."
        return f"Neenga {words} irukkudhu endru sollineenga."
    else:
        if duration:
            return f"You mentioned {words} for {duration}."
        return f"You mentioned {words}."


def _part2_symptoms(note: IntakeNote, lang: str) -> str:
    """Part 2: Stated and denied symptoms."""
    stated = [s for s in note.symptoms if s.status == FactStatus.STATED]
    denied = [s for s in note.symptoms if s.status == FactStatus.DENIED]
    unconf = [s for s in note.symptoms if s.needs_confirmation]

    parts = []
    if stated:
        names = ", ".join(s.patient_term or s.name for s in stated)
        if "hi" in lang:
            parts.append(f"Jo bimariyan aapne batayi: {names}.")
        elif "ta" in lang:
            parts.append(f"Neenga sonnadhu: {names}.")
        else:
            parts.append(f"Symptoms you mentioned: {names}.")

    if denied:
        names = ", ".join(s.patient_term or s.name for s in denied)
        if "hi" in lang:
            parts.append(f"Jo nahi hai: {names}.")
        elif "ta" in lang:
            parts.append(f"Illai endreer: {names}.")
        else:
            parts.append(f"Denied: {names}.")

    if unconf:
        names = ", ".join(s.patient_term or s.name for s in unconf)
        if "hi" in lang:
            parts.append(f"Doctor se confirm karna: {names}.")
        elif "ta" in lang:
            parts.append(f"Doctor kitta confirm pannanum: {names}.")
        else:
            parts.append(f"Please confirm with doctor: {names}.")

    return " ".join(parts) if parts else ""


def _part3_verification(note: IntakeNote, lang: str) -> str:
    """Part 3: Verification flags needing confirmation."""
    if not note.verification_flags:
        return ""
    flagged = [f for f in note.verification_flags
               if f.kind in (DriftKind.NEGATION, DriftKind.NUMBER, DriftKind.LATERALITY)]
    if not flagged:
        return ""
    refs = ", ".join(f.fact_ref for f in flagged)
    if "hi" in lang:
        return f"Kuch baatein confirm karni hain: {refs}."
    elif "ta" in lang:
        return f"Confirm pannanum: {refs}."
    else:
        return f"Please confirm: {refs}."


def _part4_gaps(note: IntakeNote, lang: str) -> str:
    """Part 4: Gaps that need follow-up (vernacular prompts)."""
    if not note.gaps:
        return ""
    # Surface the first 2 gaps in vernacular
    gap_texts = []
    for g in note.gaps[:2]:
        if g.followup_vernacular:
            gap_texts.append(g.followup_vernacular)
    if not gap_texts:
        return ""
    joined = " ".join(gap_texts)
    if "hi" in lang:
        return f"Doctor kuch aur poochh sakte hain: {joined}"
    elif "ta" in lang:
        return f"Doctor konjam kooduthal kettuvaar: {joined}"
    else:
        return f"Doctor may ask: {joined}"


def build_text(note: IntakeNote, lang: str) -> str:
    """Assemble 4-part read-back text."""
    parts = [
        _part1_complaint(note, lang),
        _part2_symptoms(note, lang),
        _part3_verification(note, lang),
        _part4_gaps(note, lang),
    ]
    return " ".join(p for p in parts if p).strip()


def build(note: IntakeNote, lang: str, ref: str) -> bytes:
    """Build read-back audio bytes via Bulbul TTS."""
    text = build_text(note, lang)
    if not text:
        text = note.chief_complaint or "Intake complete."
    return _client.tts(text, lang, ref)
