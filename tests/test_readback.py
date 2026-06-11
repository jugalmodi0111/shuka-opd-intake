import pytest
from shuka.readback import build, build_text, _part1_complaint, _part2_symptoms
from shuka.schema import (
    DriftKind, FactStatus, Gap, GapKind, HPI, IntakeNote,
    Provenance, Source, Symptom, VerificationFlag,
)


def _prov():
    return Provenance(source=Source.SPOKEN, transcript_span="x", confidence=0.9)


def _note(lang="hi-IN", symptoms=None, flags=None, gaps=None, duration="2 days"):
    return IntakeNote(
        language_detected=lang,
        chief_complaint="abdominal pain",
        chief_complaint_patient_words="pet mein dard",
        hpi=HPI(duration=duration, provenance={"duration": _prov()}),
        symptoms=symptoms or [],
        verification_flags=flags or [],
        gaps=gaps or [],
        verbatim_transcript_en="stomach pain for two days",
    )


# ── Part 1 ───────────────────────────────────────────────────────────────

def test_part1_hi_with_duration():
    note = _note("hi-IN")
    text = _part1_complaint(note, "hi-IN")
    assert "pet mein dard" in text and "2 days" in text


def test_part1_ta_without_duration():
    note = _note("ta-IN", duration=None)
    note.hpi.duration = None
    text = _part1_complaint(note, "ta-IN")
    assert "endru sollineenga" in text


# ── Part 2 ───────────────────────────────────────────────────────────────

def test_part2_stated_and_denied():
    syms = [
        Symptom(name="nausea", patient_term="ulti", status=FactStatus.STATED,
                needs_confirmation=False, provenance=_prov()),
        Symptom(name="fever", patient_term="bukhar", status=FactStatus.DENIED,
                needs_confirmation=False, provenance=_prov()),
    ]
    text = _part2_symptoms(_note(symptoms=syms), "hi-IN")
    assert "ulti" in text and "bukhar" in text
    assert "nahi" in text.lower()


def test_part2_unconfirmed_gets_confirm_prompt():
    syms = [Symptom(name="fever", patient_term="bukhar", status=FactStatus.STATED,
                    needs_confirmation=True, provenance=_prov())]
    text = _part2_symptoms(_note(symptoms=syms), "hi-IN")
    assert "confirm" in text.lower()


# ── Full text assembly ───────────────────────────────────────────────────

def test_build_text_not_empty():
    note = _note(symptoms=[
        Symptom(name="pain", patient_term="dard", status=FactStatus.STATED,
                needs_confirmation=False, provenance=_prov())
    ])
    text = build_text(note, "hi-IN")
    assert len(text) > 20


def test_build_text_tamil():
    note = _note(lang="ta-IN")
    text = build_text(note, "ta-IN")
    assert "sollineenga" in text or "endreer" in text or "irukkudhu" in text


# ── TTS integration ──────────────────────────────────────────────────────

def test_build_returns_bytes(monkeypatch):
    from shuka import readback
    monkeypatch.setattr(readback._client, "tts", lambda text, lang, ref: b"RIFF\x00\x00\x00\x00WAVEfmt ")
    audio = build(_note(), "hi-IN", "test_ref")
    assert isinstance(audio, bytes) and len(audio) > 0


def test_build_uses_tts_with_nonempty_text(monkeypatch):
    from shuka import readback
    captured = []
    monkeypatch.setattr(readback._client, "tts",
                        lambda text, lang, ref: captured.append(text) or b"X")
    note = _note(symptoms=[
        Symptom(name="pain", patient_term="dard", status=FactStatus.STATED,
                needs_confirmation=False, provenance=_prov())
    ])
    build(note, "hi-IN", "r")
    assert captured and len(captured[0]) > 5
