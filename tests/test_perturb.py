import pytest
from eval.perturb import (
    add_category_denial, all_perturbations, drop_medication,
    flip_laterality, negate_symptom, shift_duration,
)


def test_negate_symptom_inserts_nahi():
    results = negate_symptom("I have fever and cough", "fever")
    assert results and "nahi fever" in results[0][0]


def test_negate_symptom_missing_term_returns_empty():
    assert negate_symptom("stomach pain only", "headache") == []


def test_flip_laterality_left_to_right():
    results = flip_laterality("pain in left shoulder")
    assert any("right" in r[0] for r in results)
    assert all("flip_lat" in r[1] for r in results)


def test_flip_baayan_daayan():
    results = flip_laterality("baayan haath mein dard")
    assert any("daayan" in r[0] for r in results)


def test_shift_duration_two_to_five():
    results = shift_duration("pain for two days")
    assert any("five" in r[0] for r in results)


def test_drop_medication_removes_term():
    results = drop_medication("I take metformin tablet daily", "tablet")
    assert results and "tablet" not in results[0][0]


def test_category_denial_creates_echo_form():
    results = add_category_denial("bukhar tha", "bukhar", "hi")
    assert results and "bukhar-vukhar nahi" in results[0][0]


def test_all_perturbations_unique():
    results = all_perturbations(
        "fever and left arm pain for two days, takes tablet",
        lang="hi", symptom="fever", med_term="tablet", base_term="bukhar"
    )
    texts = [r[0] for r in results]
    assert len(texts) == len(set(texts))
