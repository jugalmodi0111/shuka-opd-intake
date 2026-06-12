import pytest
from shuka.followup import apply_followup, open_gaps
from shuka.schema import Gap, GapKind, HPI, IntakeNote


def _note(gaps):
    return IntakeNote(
        language_detected="hi-IN",
        chief_complaint="abdominal pain",
        chief_complaint_patient_words="pet mein dard",
        hpi=HPI(duration="2 days"),
        gaps=gaps,
        verbatim_transcript_en="stomach pain for two days",
    )


def test_hpi_gap_answer_fills_axis_and_resolves():
    note = _note([Gap(field="hpi.onset", kind=GapKind.HPI_DIMENSION,
                      followup_vernacular="Yeh kab shuru hua?")])
    out = apply_followup(note, "hpi.onset", "kal raat se")
    assert out.hpi.onset == "kal raat se"
    assert out.hpi.needs_confirmation.get("onset") is False
    assert out.gaps[0].resolved and out.gaps[0].patient_response_verbatim == "kal raat se"
    assert not open_gaps(out)


def test_answer_appends_qa_history_with_context():
    note = _note([Gap(field="symptom:dard", kind=GapKind.LEXICAL_COLLAPSE,
                      patient_term="dard", followup_vernacular="Dard kaisa hai?")])
    out = apply_followup(note, "symptom:dard", "jalan jaisa")
    assert len(out.qa_history) == 1
    turn = out.qa_history[0]
    assert turn.gap_field == "symptom:dard" and turn.answer == "jalan jaisa"
    assert turn.gap_kind == "lexical_collapse"


def test_multi_turn_accumulates_history():
    note = _note([
        Gap(field="hpi.onset", kind=GapKind.HPI_DIMENSION, followup_vernacular="Kab?"),
        Gap(field="hpi.character", kind=GapKind.HPI_DIMENSION, followup_vernacular="Kaisa?"),
    ])
    note = apply_followup(note, "hpi.onset", "do din pehle")
    note = apply_followup(note, "hpi.character", "marod jaisa")
    assert len(note.qa_history) == 2
    assert note.hpi.onset == "do din pehle" and note.hpi.character == "marod jaisa"
    assert not open_gaps(note)


def test_freetext_answer_routed_through_llm(monkeypatch):
    import json
    from shuka import followup as fu
    # Simulate Sarvam interpreting a free-text answer: normalize value + extra finding
    def fake_interpret(gap, answer, note):
        return {"field_value": "burning, cramping pain",
                "additional_findings": [{"name": "loose stools", "patient_term": "dast",
                                         "status": "stated"}],
                "summary": "x"}
    monkeypatch.setattr(fu, "_llm_interpret", fake_interpret)
    note = _note([Gap(field="hpi.character", kind=GapKind.HPI_DIMENSION,
                      followup_vernacular="Dard kaisa hai?")])
    out = fu.apply_followup(note, "hpi.character", "jalan bhi hai aur marod bhi, dast bhi ho rahe")
    # normalized value folded into the field
    assert out.hpi.character == "burning, cramping pain"
    # extra finding the patient volunteered is captured as a stated symptom
    assert any(s.name == "loose stools" for s in out.symptoms)
    # qa_history keeps the VERBATIM answer, not the normalized value
    assert out.qa_history[0].answer.startswith("jalan bhi hai")


def test_option_answer_skips_llm(monkeypatch):
    from shuka import followup as fu
    called = {"n": 0}
    monkeypatch.setattr(fu, "_llm_interpret", lambda *a: called.__setitem__("n", called["n"] + 1) or {})
    note = _note([Gap(field="hpi.character", kind=GapKind.HPI_DIMENSION,
                      followup_vernacular="Dard kaisa hai?",
                      followup_options=["jalan jaisa", "marod jaisa"])])
    fu.apply_followup(note, "hpi.character", "jalan jaisa")  # exact option → deterministic
    assert called["n"] == 0
    assert note.hpi.character == "jalan jaisa"


def test_unknown_gap_raises():
    note = _note([])
    with pytest.raises(KeyError):
        apply_followup(note, "hpi.onset", "x")


def test_already_resolved_gap_not_reanswered():
    g = Gap(field="hpi.onset", kind=GapKind.HPI_DIMENSION, resolved=True)
    note = _note([g])
    with pytest.raises(KeyError):
        apply_followup(note, "hpi.onset", "x")
