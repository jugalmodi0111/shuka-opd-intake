from shuka.verify import detect_cues, normalize_quantity


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
