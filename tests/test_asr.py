from pathlib import Path
from shuka.config import Settings
from shuka.sarvam import SarvamClient


class _FakeSTT:
    """Both witnesses go through transcribe(mode=...). translate mode → EN,
    codemix mode → original (raises here to exercise the fail-safe path)."""
    def transcribe(self, **kw):
        if kw.get("mode") == "codemix":
            raise RuntimeError("transcribe down")
        class R:
            transcript = "stomach pain"
            language_code = "hi-IN"
        return R()


class _FakeSDK:
    speech_to_text = _FakeSTT()


def test_live_translate_maps_response(monkeypatch):
    c = SarvamClient(Settings(intake_mode="live", sarvam_api_key="x"))
    monkeypatch.setattr(c, "_client_sdk", lambda: _FakeSDK())
    out = c.translate_speech(Path("samples/complaint_hinglish.wav"))
    assert out == {"transcript": "stomach pain", "language_code": "hi-IN"}


def test_transcribe_failure_surfaces_not_swallowed(monkeypatch):
    from shuka import asr
    c = SarvamClient(Settings(intake_mode="live", sarvam_api_key="x"))
    monkeypatch.setattr(c, "_client_sdk", lambda: _FakeSDK())
    monkeypatch.setattr(asr, "_client", c)
    en, orig, lang = asr.transcribe_both(Path("samples/complaint_hinglish.wav"))
    assert orig is None          # verifier will fail SAFE on this
