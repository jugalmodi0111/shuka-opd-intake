"""eval/grounding.py — Grounding audit: rate how many IntakeNote facts are
anchored to the verbatim transcript. Produces a per-case HTML report."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
from shuka.schema import FactStatus, IntakeNote  # noqa: E402


def _grounded(span: str, transcript: str) -> bool:
    """True if span (case-insensitive) appears in transcript."""
    return bool(span and span.lower() in transcript.lower())


def audit_note(note: IntakeNote) -> dict:
    """Return grounding stats for one IntakeNote."""
    total = 0
    grounded = 0
    ungrounded: list[str] = []

    tx = (note.verbatim_transcript_en or "").lower()
    tx_orig = (note.verbatim_transcript_original or "").lower()

    def check(field: str, span: str):
        nonlocal total, grounded
        total += 1
        hit = _grounded(span, tx) or _grounded(span, tx_orig)
        if hit:
            grounded += 1
        else:
            ungrounded.append(f"{field}: '{span}'")

    for s in note.symptoms:
        prov = s.provenance
        check(f"symptom:{s.name}", prov.transcript_span)

    for m in note.medications:
        prov = m.provenance
        check(f"med:{m.name}", prov.transcript_span)

    if note.hpi:
        for field, prov in (note.hpi.provenance or {}).items():
            check(f"hpi.{field}", prov.transcript_span)

    rate = grounded / total if total > 0 else 1.0
    return {
        "total_facts": total,
        "grounded_facts": grounded,
        "grounding_rate": round(rate, 3),
        "ungrounded": ungrounded,
    }


def audit_corpus(corpus_dir: Path) -> list[dict]:
    """Audit all *.json files in corpus_dir. Each must be a valid IntakeNote JSON."""
    results = []
    for p in sorted(corpus_dir.glob("*.json")):
        try:
            note = IntakeNote.model_validate(json.loads(p.read_text()))
            stats = audit_note(note)
            results.append({"file": p.name, **stats})
        except Exception as exc:
            results.append({"file": p.name, "error": str(exc)})
    return results


def render_report(results: list[dict], template_path: Path, output_path: Path) -> None:
    """Render HTML grounding report."""
    tmpl = template_path.read_text()
    rows = ""
    for r in results:
        if "error" in r:
            rows += f"<tr><td>{r['file']}</td><td colspan=3 class='err'>{r['error']}</td></tr>\n"
        else:
            cls = "ok" if r["grounding_rate"] >= 0.95 else "warn" if r["grounding_rate"] >= 0.80 else "fail"
            rows += (
                f"<tr><td>{r['file']}</td>"
                f"<td>{r['grounded_facts']}/{r['total_facts']}</td>"
                f"<td class='{cls}'>{r['grounding_rate']:.1%}</td>"
                f"<td class='ul'>{'<br>'.join(r.get('ungrounded', []))}</td></tr>\n"
            )
    html = tmpl.replace("{{ROWS}}", rows)
    output_path.write_text(html)
    print(f"Report written: {output_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="eval/corpus", help="Directory of IntakeNote JSON files")
    ap.add_argument("--output", default="eval/grounding_report.html")
    a = ap.parse_args()
    corpus_dir = Path(a.corpus)
    if not corpus_dir.exists():
        print(f"Corpus directory not found: {corpus_dir}")
        sys.exit(1)
    results = audit_corpus(corpus_dir)
    rate = sum(r.get("grounding_rate", 0) for r in results if "error" not in r)
    n = sum(1 for r in results if "error" not in r)
    avg = rate / n if n else 0
    print(f"Grounding rate: {avg:.1%} across {n} notes")
    for r in results:
        if "error" not in r and r["ungrounded"]:
            print(f"  {r['file']}: ungrounded: {r['ungrounded']}")
    template_path = Path("eval/report_template.html")
    if template_path.exists():
        render_report(results, template_path, Path(a.output))
