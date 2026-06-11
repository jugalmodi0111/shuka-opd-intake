"""eval/run_eval.py — gates exit non-zero on any failure."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from shuka.schema import IntakeNote  # noqa: E402
from shuka import verify             # noqa: E402


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--grounding", action="store_true")
    ap.add_argument("--contrast", action="store_true")
    a = ap.parse_args()
    passed = True
    if a.gates:
        passed &= corruption_gate()
        # Task 14 appends: gap_gate(); Task 15 appends: regression_gate()
    sys.exit(0 if passed else 1)
