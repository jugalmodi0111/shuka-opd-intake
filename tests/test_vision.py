from pathlib import Path
import json
import pytest
from shuka import sarvam as sarvam_mod
from shuka.vision import ALLOWED_PROMPTS, read_document
from shuka.merge import merge_document
from shuka.schema import DocumentRead, HPI, IntakeNote


# ── Prompt-allowlist spy ─────────────────────────────────────────────────

def test_allowed_prompts_is_frozenset_of_strings():
    assert isinstance(ALLOWED_PROMPTS, frozenset)
    assert all(isinstance(p, str) for p in ALLOWED_PROMPTS)
    assert len(ALLOWED_PROMPTS) == 3


def test_read_document_only_uses_allowed_prompts(tmp_path, monkeypatch):
    """Spy on SarvamClient to assert no prompt outside ALLOWED_PROMPTS is sent."""
    used_prompts = []
    fake_img = tmp_path / "rx.jpg"
    fake_img.write_bytes(b"fake")

    class _Spy:
        def classify_image(self, path, prompt):
            used_prompts.append(prompt)
            return "prescription"
        def extract_markdown(self, path, prompt):
            used_prompts.append(prompt)
            return json.dumps({"medications": [{"name": "Metformin", "dose": "500mg", "frequency": "OD"}]})

    monkeypatch.setattr(sarvam_mod, "_client", _Spy())
    read_document(fake_img)
    for p in used_prompts:
        assert p in ALLOWED_PROMPTS, f"Unauthorized prompt sent to VLM: {p!r}"


# ── read_document ────────────────────────────────────────────────────────

def test_read_prescription_returns_medications(tmp_path, monkeypatch):
    fake_img = tmp_path / "rx.jpg"
    fake_img.write_bytes(b"fake")

    class _FakeClient:
        def classify_image(self, path, prompt): return "prescription"
        def extract_markdown(self, path, prompt):
            return json.dumps({"medications": [
                {"name": "Metformin", "dose": "500mg", "frequency": "OD"},
                {"name": "Amlodipine", "dose": "5mg", "frequency": "BD"},
            ]})

    monkeypatch.setattr(sarvam_mod, "_client", _FakeClient())
    doc = read_document(fake_img)
    assert doc.doc_type == "prescription"
    assert len(doc.medications) == 2
    assert doc.medications[0]["name"] == "Metformin"


def test_read_lab_returns_labs(tmp_path, monkeypatch):
    fake_img = tmp_path / "lab.jpg"
    fake_img.write_bytes(b"fake")

    class _FakeClient:
        def classify_image(self, path, prompt): return "lab_report"
        def extract_markdown(self, path, prompt):
            return json.dumps({"labs": [
                {"name": "HbA1c", "value": "7.2", "unit": "%", "flag": "H", "reference": "<5.7"}
            ]})

    monkeypatch.setattr(sarvam_mod, "_client", _FakeClient())
    doc = read_document(fake_img)
    assert doc.doc_type == "lab_report"
    assert doc.labs[0]["name"] == "HbA1c"


def test_unknown_doc_type_returns_other(tmp_path, monkeypatch):
    fake_img = tmp_path / "x.jpg"
    fake_img.write_bytes(b"fake")

    class _FakeClient:
        def classify_image(self, path, prompt): return "other"
        def extract_markdown(self, path, prompt): return ""

    monkeypatch.setattr(sarvam_mod, "_client", _FakeClient())
    doc = read_document(fake_img)
    assert doc.doc_type == "other"


# ── merge_document ───────────────────────────────────────────────────────

def _note_stub():
    return IntakeNote(
        language_detected="hi-IN",
        chief_complaint="stomach pain",
        chief_complaint_patient_words="pet mein dard",
        hpi=HPI(duration="2 days"),
        verbatim_transcript_en="stomach pain for two days, I take BP medicine",
    )


def test_merge_adds_medications_from_prescription():
    note = _note_stub()
    doc = DocumentRead(
        doc_type="prescription",
        raw_text="",
        medications=[{"name": "Metformin", "dose": "500mg", "frequency": "OD"}],
        labs=[],
    )
    merged = merge_document(note, doc)
    names = [m.name for m in merged.medications]
    assert "Metformin" in names
    met = next(m for m in merged.medications if m.name == "Metformin")
    assert met.needs_confirmation is True


def test_merge_does_not_duplicate_existing_medication():
    from shuka.schema import Medication, Provenance, Source
    note = _note_stub()
    note.medications.append(Medication(
        name="Metformin", patient_term="sugar ki dawai",
        dose="500mg", frequency="OD",
        needs_confirmation=False,
        provenance=Provenance(source=Source.SPOKEN, transcript_span="sugar ki dawai", confidence=0.9)
    ))
    doc = DocumentRead(
        doc_type="prescription", raw_text="",
        medications=[{"name": "Metformin", "dose": "500mg", "frequency": "OD"}],
        labs=[],
    )
    merged = merge_document(note, doc)
    mets = [m for m in merged.medications if m.name == "Metformin"]
    assert len(mets) == 1  # no duplicate


def test_merge_marks_confirmation_on_dose_conflict():
    from shuka.schema import Medication, Provenance, Source
    note = _note_stub()
    note.medications.append(Medication(
        name="Metformin", patient_term="sugar ki dawai",
        dose="250mg",  # differs from document
        frequency="OD",
        needs_confirmation=False,
        provenance=Provenance(source=Source.SPOKEN, transcript_span="sugar ki dawai", confidence=0.9)
    ))
    doc = DocumentRead(
        doc_type="prescription", raw_text="",
        medications=[{"name": "Metformin", "dose": "500mg", "frequency": "OD"}],
        labs=[],
    )
    merged = merge_document(note, doc)
    met = next(m for m in merged.medications if m.name == "Metformin")
    assert met.needs_confirmation is True
