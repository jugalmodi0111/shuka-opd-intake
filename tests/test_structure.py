import json
import pytest
from shuka import structure
from shuka.schema import FactStatus, IntakeNote


def _good_note() -> dict:
    """Minimal valid IntakeNote JSON."""
    return {
        "language_detected": "hi-IN",
        "chief_complaint": "abdominal pain",
        "chief_complaint_patient_words": "pet mein dard",
        "hpi": {
            "duration": "2 days",
            "provenance": {
                "duration": {
                    "source": "spoken",
                    "transcript_span": "two days",
                    "confidence": 0.9,
                }
            },
        },
        "symptoms": [
            {
                "name": "abdominal pain",
                "patient_term": "pet mein dard",
                "status": "stated",
                "needs_confirmation": False,
                "provenance": {
                    "source": "spoken",
                    "transcript_span": "stomach pain",
                    "confidence": 0.95,
                },
            }
        ],
        "verbatim_transcript_en": "stomach pain for two days",
    }


def test_build_note_happy_path(monkeypatch):
    monkeypatch.setattr(structure, "_chat", lambda msgs: json.dumps(_good_note()))
    note = structure.build_note("stomach pain for two days", "hi-IN", "ref1")
    assert isinstance(note, IntakeNote)
    assert note.chief_complaint == "abdominal pain"
    assert note.verbatim_transcript_en == "stomach pain for two days"


def test_repair_loop_retries_on_bad_json(monkeypatch):
    calls = [0]

    def flaky(msgs):
        calls[0] += 1
        if calls[0] < 2:
            return "not json at all"
        return json.dumps(_good_note())

    monkeypatch.setattr(structure, "_chat", flaky)
    note = structure.build_note("stomach pain for two days", "hi-IN", "ref2")
    assert note.chief_complaint == "abdominal pain"
    assert calls[0] == 2


def test_repair_loop_fails_after_3_attempts(monkeypatch):
    monkeypatch.setattr(structure, "_chat", lambda msgs: "{{bad json}}")
    with pytest.raises(RuntimeError, match="3 repair attempts"):
        structure.build_note("stomach pain for two days", "hi-IN", "ref3")


def test_regression_no_inferred_facts(monkeypatch):
    """Zero facts in the output that have no basis in the transcript."""
    transcript = "I have stomach pain for two days"
    monkeypatch.setattr(structure, "_chat", lambda msgs: json.dumps(_good_note()))
    note = structure.build_note(transcript, "en", "ref4")
    # Every stated/denied symptom must appear in the transcript
    for s in note.symptoms:
        if s.status in (FactStatus.STATED, FactStatus.DENIED):
            name_lower = s.name.lower()
            term_lower = (s.patient_term or "").lower()
            in_transcript = (
                name_lower in transcript.lower() or
                term_lower in transcript.lower() or
                any(w in transcript.lower() for w in name_lower.split())
            )
            assert in_transcript, (
                f"Inferred fact '{s.name}' not grounded in transcript: '{transcript}'"
            )


def test_markdown_fences_stripped(monkeypatch):
    fenced = "```json\n" + json.dumps(_good_note()) + "\n```"
    monkeypatch.setattr(structure, "_chat", lambda msgs: fenced)
    note = structure.build_note("stomach pain for two days", "hi-IN", "ref5")
    assert note.chief_complaint == "abdominal pain"
