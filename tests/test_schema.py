import pytest
from pydantic import ValidationError
from shuka.schema import (DriftKind, FactStatus, Gap, GapKind, HPI,
                              IntakeNote, Provenance, Source, Symptom,
                              VerificationFlag)


def _prov():
    return Provenance(source=Source.SPOKEN, transcript_span="no fever", confidence=0.9)


def test_stated_symptom_requires_provenance():
    with pytest.raises(ValidationError):
        Symptom(name="fever", status=FactStatus.DENIED)


def test_not_mentioned_symptom_rejected_in_note():
    s = Symptom(name="fever", status=FactStatus.NOT_MENTIONED)
    with pytest.raises(ValidationError):
        IntakeNote(language_detected="hi-IN", chief_complaint="abdominal pain",
                   chief_complaint_patient_words="pet mein dard", hpi=HPI(),
                   symptoms=[s], verbatim_transcript_en="x")


def test_leads_diagnosis_hard_fails():
    with pytest.raises(ValidationError):
        Gap(field="symptom:gas", kind=GapKind.LEXICAL_COLLAPSE, leads_diagnosis=True)


def test_flag_without_needs_confirmation_rejected():
    flag = VerificationFlag(fact_ref="fever", kind=DriftKind.NEGATION, detail="nahi dropped")
    with pytest.raises(ValidationError):
        IntakeNote(language_detected="hi-IN", chief_complaint="pain",
                   chief_complaint_patient_words="dard", hpi=HPI(),
                   verification_flags=[flag], verbatim_transcript_en="x")


def test_flag_with_confirmed_fact_passes():
    flag = VerificationFlag(fact_ref="fever", kind=DriftKind.NEGATION, detail="nahi dropped")
    s = Symptom(name="fever", status=FactStatus.DENIED, needs_confirmation=True,
                provenance=_prov())
    note = IntakeNote(language_detected="hi-IN", chief_complaint="pain",
                      chief_complaint_patient_words="dard", hpi=HPI(),
                      symptoms=[s], verification_flags=[flag], verbatim_transcript_en="x")
    assert note.symptoms[0].needs_confirmation
