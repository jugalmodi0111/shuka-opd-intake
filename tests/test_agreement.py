import json, math
import pytest
from eval.agreement import cohen_kappa, load_clip_annotation, run_agreement
from pathlib import Path


def test_kappa_perfect_agreement():
    a = ["stated", "denied", "stated", "unconfirmed"]
    assert cohen_kappa(a, a) == pytest.approx(1.0)


def test_kappa_chance_agreement():
    # Systematic disagreement with balanced marginals → κ negative (worse than chance).
    # (All-stated vs all-denied is degenerate: p_e=0 ⇒ κ=0, not negative.)
    a = ["stated", "denied", "stated", "denied"]
    b = ["denied", "stated", "denied", "stated"]
    k = cohen_kappa(a, b)
    assert k < 0


def test_kappa_partial_agreement():
    # p_o=0.75, p_e=0.5 ⇒ κ=0.5. (Symmetric swap data gives p_o==p_e ⇒ κ=0.)
    a = ["stated", "stated", "stated", "denied"]
    b = ["stated", "stated", "denied", "denied"]
    k = cohen_kappa(a, b)
    assert 0 < k < 1


def test_kappa_empty_returns_nan():
    assert math.isnan(cohen_kappa([], []))


def test_kappa_length_mismatch_raises():
    with pytest.raises(ValueError):
        cohen_kappa(["a", "b"], ["a"])


def test_run_agreement_no_clips(tmp_path):
    result = run_agreement(tmp_path)
    assert result["n_clips"] == 0
    assert result["overall_kappa"] is None


def test_run_agreement_with_synthetic_clip(tmp_path):
    clip = {
        "clip_id": "clip_001",
        "verifier_labels": ["stated", "stated", "denied"],
        "human_labels":    ["stated", "denied",  "denied"],
    }
    (tmp_path / "clip_001.json").write_text(json.dumps(clip))
    result = run_agreement(tmp_path)
    assert result["n_clips"] == 1
    assert result["n_facts"] == 3
    assert result["overall_kappa"] is not None
    assert "correlated omission" in result["note"].lower()
