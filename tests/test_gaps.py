import datetime

from shuka.config import settings
from shuka.gaps import (
    Lexicons,
    detect_category_denial,
    detect_frequency_drop,
    detect_hpi_dimension,
    detect_lexical_collapse,
    detect_register_switch,
    detect_temporal_anchor,
)
from shuka.schema import GapKind, HPI, IntakeNote

LEX = Lexicons.load(settings.lexicon_dir)


# ── Task 10 ───────────────────────────────────────────────────────────────────

def test_lexicons_load_and_are_consistent():
    assert "chakkar" in LEX.collapse_map["hi"]
    entry = LEX.collapse_map["hi"]["chakkar"]
    assert len(entry["referents"]) >= 3 and entry["probe"] and entry["options"]
    assert LEX.festival_date("holi", 2026).month == 3
    assert LEX.festival_date("pongal", 2026) == LEX.festival_date("bihu", 2026)
    assert "v" in LEX.echo_onsets["hi"]
    assert not (set(LEX.phenomenology_whitelist) & set(LEX.symptom_names))


# ── Task 11 ───────────────────────────────────────────────────────────────────

def test_chakkar_collapse_detected_with_phenomenology_followup():
    gaps = detect_lexical_collapse("do din se chakkar aa raha hai", "hi-IN", LEX)
    g = gaps[0]
    assert g.kind == GapKind.LEXICAL_COLLAPSE and g.patient_term == "chakkar"
    assert "ghoom" in g.followup_vernacular
    assert g.followup_options and g.source_stream == "original"


def test_collapse_invisible_on_english_stream():
    assert detect_lexical_collapse("feeling dizzy for two days", "en", LEX) == []


def test_echo_negation_is_category_denial():
    gaps = detect_category_denial("bukhar-vukhar nahi tha", "hi-IN", LEX)
    g = gaps[0]
    assert g.kind == GapKind.CATEGORY_DENIAL and g.patient_term == "bukhar-vukhar"


def test_plain_negation_is_not_category_denial():
    assert detect_category_denial("bukhar nahi tha", "hi-IN", LEX) == []


def test_pro_drop_event_without_count_is_frequency_gap():
    gaps = detect_frequency_drop("kal raat ulti hui", "hi-IN", LEX)
    assert gaps[0].kind == GapKind.FREQUENCY_DROP and "kitni baar" in gaps[0].followup_vernacular.lower()


def test_counted_event_is_not_a_gap():
    assert detect_frequency_drop("ek baar ulti hui", "hi-IN", LEX) == []


# ── Task 12 ───────────────────────────────────────────────────────────────────

ENCOUNTER = datetime.date(2026, 3, 25)


def test_holi_anchor_resolves_to_candidate_with_confirmation():
    gaps = detect_temporal_anchor("holi ke baad se chakkar aa raha hai", "hi-IN", LEX, ENCOUNTER)
    g = gaps[0]
    assert g.kind == GapKind.TEMPORAL_ANCHOR and "holi" in g.patient_term
    assert "~21 days" in g.resolution_candidate
    assert "andaaza" in g.followup_vernacular


def test_alias_pongal_resolves_via_winter_harvest():
    gaps = detect_temporal_anchor("pongal time la irundhu kai valikkudhu", "ta-IN",
                                  LEX, datetime.date(2026, 2, 1))
    assert len(gaps) > 0 and "days" in gaps[0].resolution_candidate


def test_no_anchor_no_gap():
    assert detect_temporal_anchor("do din se dard hai", "hi-IN", LEX, ENCOUNTER) == []


# ── Task 13 ───────────────────────────────────────────────────────────────────

def test_code_switch_bp_marks_borrowed_register():
    gaps = detect_register_switch("main BP ki dawai leta hoon, sugar hai", "hi-IN", LEX)
    sugar = next(g for g in gaps if g.patient_term == "sugar")
    assert sugar.kind == GapKind.REGISTER_AMBIG
    assert "doctor ne bataya" in sugar.followup_vernacular


def test_somatic_idiom_gets_neutral_probe():
    gaps = detect_register_switch("dil baith raha hai", "hi-IN", LEX)
    assert gaps[0].kind == GapKind.REGISTER_AMBIG
    assert "dil baith" in gaps[0].followup_vernacular


def test_missing_hpi_fields_become_dimension_gaps():
    note = IntakeNote(language_detected="hi-IN", chief_complaint="abdominal pain",
                      chief_complaint_patient_words="pet mein dard",
                      hpi=HPI(duration="2 days"), verbatim_transcript_en="x")
    gaps = detect_hpi_dimension(note)
    fields = {g.field for g in gaps}
    assert "hpi.onset" in fields and "hpi.character" in fields
    assert "hpi.duration" not in fields
    char = next(g for g in gaps if g.field == "hpi.character")
    assert "jalan" in char.followup_vernacular
