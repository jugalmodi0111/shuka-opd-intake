"""eval/wiring_check.py — live guardrail.

Verifies, WITHOUT touching the network:
  1. Every Sarvam model seam is wired in live mode (chat / TTS / both STT witnesses)
     by monkeypatching a fake SDK and asserting the live branch calls it with the
     right method + kwargs — i.e. NO NotImplementedError on the mandatory path.
  2. The FastAPI server exposes every route the UI calls.
  3. web/index.html actually calls those routes.

Run:  uv run python eval/wiring_check.py        (exits non-zero on any failure)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

_ROOT = Path(__file__).resolve().parent.parent
_WEB = _ROOT / "web" / "index.html"


# ── 1. Sarvam model wiring (fake SDK, no network) ────────────────────────

class _RecordingSTT:
    def __init__(self, sink): self._sink = sink
    def transcribe(self, **kw):
        self._sink.append(("stt.transcribe", kw))
        class R:
            transcript = "stomach pain for two days"
            language_code = "hi-IN"
        return R()


class _RecordingChat:
    def __init__(self, sink): self._sink = sink
    def completions(self, **kw):
        self._sink.append(("chat.completions", kw))
        class Msg: content = '{"ok": true}'
        class Ch: message = Msg()
        class R: choices = [Ch()]
        return R()


class _RecordingTTS:
    def __init__(self, sink): self._sink = sink
    def convert(self, **kw):
        self._sink.append(("tts.convert", kw))
        import base64
        class R: audios = [base64.b64encode(b"RIFFwav").decode()]
        return R()


class _FakeSDK:
    def __init__(self):
        self.calls = []
        self.speech_to_text = _RecordingSTT(self.calls)
        self.chat = _RecordingChat(self.calls)
        self.text_to_speech = _RecordingTTS(self.calls)


def check_models() -> list[tuple[str, bool, str]]:
    from shuka.config import Settings
    from shuka.sarvam import SarvamClient

    out: list[tuple[str, bool, str]] = []
    c = SarvamClient(Settings(intake_mode="live", sarvam_api_key="x"))
    sdk = _FakeSDK()
    c._client_sdk = lambda: sdk  # type: ignore[method-assign]
    audio = Path("samples/complaint_hinglish.wav")

    # English witness — must call transcribe(mode='translate')
    try:
        r = c.translate_speech(audio)
        ok = r["transcript"] and any(
            m == "stt.transcribe" and kw.get("mode") == "translate" for m, kw in sdk.calls)
        out.append(("Saaras v3 — translate (EN witness)", bool(ok),
                    "transcribe(mode=translate)"))
    except Exception as e:
        out.append(("Saaras v3 — translate (EN witness)", False, f"{type(e).__name__}: {e}"))

    sdk.calls.clear()
    # Original witness — must call transcribe(mode='codemix')
    try:
        r = c.transcribe_speech(audio)
        ok = r["transcript"] and any(
            m == "stt.transcribe" and kw.get("mode") == "codemix" for m, kw in sdk.calls)
        out.append(("Saaras v3 — codemix (original witness)", bool(ok),
                    "transcribe(mode=codemix)"))
    except Exception as e:
        out.append(("Saaras v3 — codemix (original witness)", False, f"{type(e).__name__}: {e}"))

    sdk.calls.clear()
    # Sarvam-M chat
    try:
        txt = c.chat([{"role": "user", "content": "hi"}], stage="structure", ref="r")
        ok = txt and any(m == "chat.completions" and kw.get("model") for m, kw in sdk.calls)
        out.append(("Sarvam-M — chat.completions", bool(ok), "model passed"))
    except Exception as e:
        out.append(("Sarvam-M — chat.completions", False, f"{type(e).__name__}: {e}"))

    sdk.calls.clear()
    # Bulbul TTS
    try:
        b = c.tts("Aapne bataya ki aapko dard hai.", "hi-IN", "r")
        ok = isinstance(b, bytes) and len(b) > 0 and any(
            m == "tts.convert" and kw.get("target_language_code") == "hi-IN" for m, kw in sdk.calls)
        out.append(("Bulbul v3 — tts.convert", bool(ok), "target_language_code=hi-IN, wav"))
    except Exception as e:
        out.append(("Bulbul v3 — tts.convert", False, f"{type(e).__name__}: {e}"))

    return out


# ── 2. Server routes ─────────────────────────────────────────────────────

def check_routes() -> list[tuple[str, bool, str]]:
    from shuka.server import app
    paths = {getattr(r, "path", "") for r in app.routes}
    want = ["/", "/mode", "/samples", "/samples/{name}", "/intake", "/favicon.ico"]
    return [(f"route {p}", p in paths, "mounted") for p in want] + [
        ("mount /assets", any(getattr(r, "path", "").startswith("/assets") for r in app.routes),
         "static mount")]


# ── 3. UI calls the routes ───────────────────────────────────────────────

def check_ui() -> list[tuple[str, bool, str]]:
    html = _WEB.read_text() if _WEB.exists() else ""
    checks = {
        "UI posts to /intake": "'/intake'" in html or '"/intake"' in html,
        "UI fetches /mode": "/mode" in html,
        "UI fetches /samples/": "/samples/" in html,
        "UI references real sample names": "complaint_hinglish.wav" in html,
        "UI uses MediaRecorder (real mic)": "MediaRecorder" in html,
        "UI renders followup_vernacular": "followup_vernacular" in html,
        "UI reads verbatim_transcript_en": "verbatim_transcript_en" in html,
        "Correlated-omission disclaimer present": "orrelated omission" in html,
    }
    return [(k, v, "found" if v else "MISSING") for k, v in checks.items()]


def check_live_smoke() -> list[tuple[str, bool, str]]:
    """Real round-trip per model — catches API-side breakages (deprecated model,
    invalid speaker) that the fake-SDK check cannot. Costs a few API calls."""
    from shuka.config import Settings
    from shuka.sarvam import SarvamClient

    out: list[tuple[str, bool, str]] = []
    c = SarvamClient(Settings(intake_mode="live"))
    audio = Path("samples/complaint_hinglish.wav")
    try:
        r = c.translate_speech(audio)
        out.append(("Saaras translate (real)", bool(r.get("transcript")), r.get("transcript", "")[:40]))
    except Exception as e:
        out.append(("Saaras translate (real)", False, str(e)[-80:]))
    try:
        r = c.transcribe_speech(audio)
        out.append(("Saaras codemix (real)", bool(r.get("transcript")), r.get("transcript", "")[:40]))
    except Exception as e:
        out.append(("Saaras codemix (real)", False, str(e)[-80:]))
    try:
        txt = c.chat([{"role": "user", "content": "Return JSON {\"ok\":true} only"}],
                     stage="structure", ref="smoke")
        out.append(("Sarvam-M chat (real)", bool(txt), txt[:40]))
    except Exception as e:
        out.append(("Sarvam-M chat (real)", False, str(e)[-80:]))
    try:
        b = c.tts("namaste", "hi-IN", "smoke")
        out.append(("Bulbul TTS (real)", isinstance(b, bytes) and len(b) > 100, f"{len(b)} bytes"))
    except Exception as e:
        out.append(("Bulbul TTS (real)", False, str(e)[-80:]))
    return out


def main() -> int:
    live = "--live" in sys.argv
    sections = [
        ("SARVAM MODELS (live wiring, no network)", check_models()),
        ("SERVER ROUTES", check_routes()),
        ("UI WIRING", check_ui()),
    ]
    if live:
        sections.append(("SARVAM MODELS (REAL API smoke test)", check_live_smoke()))
    all_ok = True
    for title, rows in sections:
        print(f"\n{title}")
        print("-" * 60)
        for name, ok, detail in rows:
            all_ok &= ok
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:<46} {detail}")
    print("\n" + ("=" * 60))
    print("WIRING GUARDRAIL:", "PASS — UI and all Sarvam models wired" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
