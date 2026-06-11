from shuka.schema import (DriftKind, FactStatus, HPI, IntakeNote,
                          Provenance, Source, Symptom)
from shuka.verify import VerificationReport, cross_check, detect_cues, normalize_quantity, verify_facts


def test_negation_cue_hindi_with_anchor():
    cues = detect_cues("bukhar nahi tha, pet mein dard hai", "hi-IN")
    neg = cues.negations[0]
    assert neg.surface in ("nahi", "नहीं") and neg.anchor == "bukhar"


def test_negation_cue_english():
    cues = detect_cues("no fever, stomach pain", "en")
    assert cues.negations[0].anchor == "fever"


def test_laterality_hindi():
    cues = detect_cues("baayan haath mein dard", "hi-IN")
    assert cues.lateralities[0].surface == "baayan"


def test_indic_colloquial_quantity_dhai():
    cues = detect_cues("dhai din se dard hai", "hi-IN")
    assert cues.numbers[0].value == 2.5 and cues.numbers[0].anchor == "din"


def test_paune_compound():
    assert normalize_quantity("paune do") == 1.75
    assert normalize_quantity("dedh") == 1.5
    assert normalize_quantity("two") == 2.0
    assert normalize_quantity("rendu") == 2.0


def test_echo_form_still_yields_negation_anchor():
    cues = detect_cues("bukhar-vukhar nahi tha", "hi-IN")
    assert cues.negations[0].anchor == "bukhar-vukhar"


def test_dropped_negation_flagged():
    orig = detect_cues("bukhar nahi tha", "hi-IN")
    en = detect_cues("had fever", "en")
    report = cross_check(orig, en)
    assert any(f.kind == DriftKind.NEGATION for f in report.flags)
    assert report.flags[0].original_evidence is not None


def test_matched_negation_not_flagged():
    orig = detect_cues("bukhar nahi tha", "hi-IN")
    en = detect_cues("no fever", "en")
    assert not cross_check(orig, en).flags


def test_number_value_drift():
    orig = detect_cues("dhai din se dard", "hi-IN")
    en = detect_cues("pain for two days", "en")
    report = cross_check(orig, en)
    assert any(f.kind == DriftKind.NUMBER for f in report.flags)


def test_laterality_missing_in_en():
    orig = detect_cues("baayan haath mein dard", "hi-IN")
    en = detect_cues("pain in the hand", "en")
    report = cross_check(orig, en)
    assert any(f.kind == DriftKind.LATERALITY for f in report.flags)


def test_missing_original_is_fail_safe_not_fail_open():
    report = cross_check(None, detect_cues("no fever", "en"))
    assert report.verified is False


def _note2(symptoms):
    return IntakeNote(language_detected="hi-IN", chief_complaint="stomach pain",
                      chief_complaint_patient_words="pet mein dard",
                      hpi=HPI(duration="2 days",
                              provenance={"duration": Provenance(source=Source.SPOKEN,
                                          transcript_span="two days", confidence=0.9)}),
                      symptoms=symptoms, verbatim_transcript_en="had fever, pain for two days")


def _fever2(status):
    return Symptom(name="fever", patient_term="bukhar", status=status,
                   provenance=Provenance(source=Source.SPOKEN, transcript_span="fever",
                                         confidence=0.9))


def test_negation_drift_marks_fact_unconfirmed():
    orig = detect_cues("bukhar nahi tha, do din se dard", "hi-IN")
    en = detect_cues("had fever, pain for two days", "en")
    note = verify_facts(_note2([_fever2(FactStatus.STATED)]),
                        cross_check(orig, en),
                        "had fever, pain for two days", "bukhar nahi tha, do din se dard")
    fever = note.symptoms[0]
    assert fever.needs_confirmation
    assert any(f.kind == DriftKind.NEGATION and f.fact_ref == "fever"
               for f in note.verification_flags)


def test_fail_safe_marks_all_safety_critical():
    report = VerificationReport(flags=[], verified=False)
    note = verify_facts(_note2([_fever2(FactStatus.DENIED)]), report,
                        "no fever, pain for two days", None)
    assert note.symptoms[0].needs_confirmation
    assert note.hpi.needs_confirmation.get("duration") is True
    assert all(f.kind == DriftKind.UNVERIFIED for f in note.verification_flags)
