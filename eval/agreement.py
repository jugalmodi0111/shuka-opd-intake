"""eval/agreement.py — Correlated-omission measurement infrastructure.

Measures inter-rater agreement between:
  - verifier_flags: facts flagged by the two-witness verifier
  - human_flags: facts flagged by a human reviewer

Computes Cohen's κ (kappa) over fact-level STATED/DENIED/UNCONFIRMED classifications.

Usage:
    python eval/agreement.py --clips eval/realclips --output eval/agreement_report.json

Real clips require manual consent collection per CONSENT.md.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def cohen_kappa(rater_a: list[str], rater_b: list[str]) -> float:
    """Compute Cohen's κ for two parallel lists of categorical labels."""
    if len(rater_a) != len(rater_b):
        raise ValueError("Rater lists must be same length.")
    if not rater_a:
        return float("nan")

    categories = sorted(set(rater_a) | set(rater_b))
    n = len(rater_a)
    # Observed agreement
    p_o = sum(a == b for a, b in zip(rater_a, rater_b)) / n
    # Expected agreement
    p_e = sum(
        (rater_a.count(c) / n) * (rater_b.count(c) / n) for c in categories
    )
    if abs(1 - p_e) < 1e-9:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def load_clip_annotation(path: Path) -> dict:
    """Load a clip annotation JSON. Schema:
    {
      "clip_id": "clip_001",
      "verifier_labels": ["stated", "stated", "denied", ...],
      "human_labels":    ["stated", "stated", "denied", ...],
      "notes": "optional"
    }
    """
    return json.loads(path.read_text())


def run_agreement(clips_dir: Path) -> dict:
    """Compute agreement over all annotation files in clips_dir."""
    all_verifier: list[str] = []
    all_human: list[str] = []
    per_clip: list[dict] = []

    for p in sorted(clips_dir.glob("*.json")):
        if p.name == "CONSENT.md":
            continue
        try:
            ann = load_clip_annotation(p)
        except Exception as exc:
            per_clip.append({"clip": p.name, "error": str(exc)})
            continue
        v = ann.get("verifier_labels", [])
        h = ann.get("human_labels", [])
        if len(v) != len(h):
            per_clip.append({"clip": p.name, "error": "label list length mismatch"})
            continue
        kappa = cohen_kappa(v, h)
        per_clip.append({
            "clip": p.name,
            "n_facts": len(v),
            "kappa": round(kappa, 3) if not math.isnan(kappa) else None,
        })
        all_verifier.extend(v)
        all_human.extend(h)

    overall_kappa = None
    if all_verifier:
        k = cohen_kappa(all_verifier, all_human)
        overall_kappa = round(k, 3) if not math.isnan(k) else None

    return {
        "n_clips": len(per_clip),
        "n_facts": len(all_verifier),
        "overall_kappa": overall_kappa,
        "per_clip": per_clip,
        "note": (
            "Correlated omission — when both ASR views miss the same utterance — "
            "is the dominant failure mode in real acoustic conditions and cannot "
            "be caught by the verifier. κ here measures verifier-vs-human agreement "
            "on heard utterances only."
        ),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default="eval/realclips")
    ap.add_argument("--output", default="eval/agreement_report.json")
    a = ap.parse_args()

    clips_dir = Path(a.clips)
    if not clips_dir.exists():
        print(f"Clips dir not found: {clips_dir}  (manual consent collection required)")
        sys.exit(0)

    result = run_agreement(clips_dir)
    out = Path(a.output)
    out.write_text(json.dumps(result, indent=2))
    print(f"Agreement report: {out}")
    if result["overall_kappa"] is not None:
        print(f"Overall κ = {result['overall_kappa']} over {result['n_facts']} facts")
    else:
        print("No annotated clips found — κ cannot be computed yet")
