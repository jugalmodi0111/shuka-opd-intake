"""eval/run_eval.py — gates exit non-zero on any failure."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from shuka.schema import FactStatus, HPI, IntakeNote  # noqa: E402
from shuka import verify             # noqa: E402
from shuka.config import settings    # noqa: E402
from shuka.gaps import Lexicons, detect_gaps  # noqa: E402

_LEX = Lexicons.load(settings.lexicon_dir)


def corruption_gate() -> bool:
    ok = True
    for p in sorted(Path("eval/corruption").glob("*.json")):
        case = json.loads(p.read_text())
        lang = case.get("lang", "hi-IN")
        report = verify.cross_check(
            verify.detect_cues(case["transcript_original"], lang),
            verify.detect_cues(case["transcript_en"], "en"))
        got = {f.kind.value for f in report.flags}
        want = {e["kind"] for e in case["expected_flags"]}
        if not want <= got:
            print(f"FAIL {p.name}: wanted {want}, got {got}")
            ok = False
        else:
            print(f"PASS {p.name}: {got}")
    print("corruption gate:", "PASS" if ok else "FAIL")
    return ok


def gap_gate() -> bool:
    """Benchmark detect_gaps: zero leading gaps + vernacular recall on collapse terms.
    LLM fallback disabled here (mock-safe) so the gate is deterministic."""
    import shuka.gaps as _g
    orig_probe = _g.llm_probe_unknown_collapse
    _g.llm_probe_unknown_collapse = lambda *a, **kw: None
    ok = True
    try:
        for p in sorted(Path("eval/gaps").glob("*.json")):
            case = json.loads(p.read_text())
            lang = case.get("lang", "hi-IN")
            note = IntakeNote(
                language_detected=lang,
                chief_complaint=case.get("chief_complaint", "complaint"),
                chief_complaint_patient_words=case.get("chief_complaint", "complaint"),
                hpi=HPI(duration=case.get("hpi_duration")),
                verbatim_transcript_en=case["transcript_en"],
            )
            gaps = detect_gaps(note, case["transcript_original"], lang, _LEX,
                               settings.encounter_date)
            a = case.get("assertions", {})

            # Non-leading invariant — the load-bearing safety gate
            n_leading = sum(1 for x in gaps if x.leads_diagnosis)
            if "leading" in a and n_leading != a["leading"]:
                print(f"FAIL {p.name}: leading={n_leading}, want {a['leading']}")
                ok = False

            kinds = {x.kind.value for x in gaps}
            for want_kind in a.get("gap_kinds_present", []):
                if want_kind not in kinds:
                    print(f"FAIL {p.name}: missing gap kind '{want_kind}' (got {kinds})")
                    ok = False

            terms = {x.patient_term for x in gaps}
            for want_term in a.get("patient_terms", []):
                if want_term not in terms:
                    print(f"FAIL {p.name}: missing patient_term '{want_term}' (got {terms})")
                    ok = False

            needle = a.get("followup_must_contain")
            if needle and not any(needle in (x.followup_vernacular or "") for x in gaps):
                print(f"FAIL {p.name}: no followup contains '{needle}'")
                ok = False

            if ok:
                print(f"PASS {p.name}: kinds={kinds} leading={n_leading}")
    finally:
        _g.llm_probe_unknown_collapse = orig_probe
    print("gap gate:", "PASS" if ok else "FAIL")
    return ok


def regression_gate() -> bool:
    """Zero inferred facts: every stated/denied fact must be grounded in the transcript."""
    ok = True
    for p in sorted(Path("eval/corpus").glob("*.json")):
        note = IntakeNote.model_validate(json.loads(p.read_text()))
        tx = (note.verbatim_transcript_en or "").lower()
        txo = (note.verbatim_transcript_original or "").lower()
        for s in note.symptoms:
            if s.status in (FactStatus.STATED, FactStatus.DENIED):
                span = (s.provenance.transcript_span or "").lower() if s.provenance else ""
                if span and span not in tx and span not in txo:
                    print(f"FAIL {p.name}: inferred fact '{s.name}' span '{span}' not in transcript")
                    ok = False
        if ok:
            print(f"PASS {p.name}: all facts grounded")
    print("regression gate:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--grounding", action="store_true")
    ap.add_argument("--contrast", action="store_true")
    a = ap.parse_args()
    passed = True
    if a.gates:
        passed &= corruption_gate()
        passed &= gap_gate()
        passed &= regression_gate()
    sys.exit(0 if passed else 1)
