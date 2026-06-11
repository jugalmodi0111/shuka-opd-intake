from pathlib import Path
from shuka.config import settings
from shuka.sarvam import SarvamClient

_client = SarvamClient(settings)


def transcribe_both(audio: Path) -> tuple[str, str | None, str]:
    """Returns (transcript_en, transcript_original, language_detected).
    transcript_original=None signals the verifier to fail SAFE."""
    t = _client.translate_speech(audio)
    en, lang = t["transcript"], t.get("language_code", "unknown")
    try:
        orig = _client.transcribe_speech(audio)["transcript"]
    except Exception:
        orig = None     # never silently skip verification; verifier fail-safes
    return en, orig, lang
