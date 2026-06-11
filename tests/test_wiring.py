"""Guardrail in the test suite — fails CI if any model seam or UI route regresses."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import wiring_check  # noqa: E402


def test_all_sarvam_models_wired_live():
    for name, ok, detail in wiring_check.check_models():
        assert ok, f"model seam not wired: {name} — {detail}"


def test_server_routes_present():
    for name, ok, detail in wiring_check.check_routes():
        assert ok, f"missing {name}"


def test_ui_wired_to_endpoints():
    for name, ok, detail in wiring_check.check_ui():
        assert ok, f"UI wiring: {name} — {detail}"
