from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shuka.config import settings
from shuka.sarvam import SarvamClient

_client = SarvamClient(settings)


def transcribe_both(audio: Path) -> tuple[str, str | None, str]:
    """Returns (transcript_en, transcript_original, language_detected).

    The two Saaras passes are independent, so they run concurrently — halves ASR
    wall-clock. transcript_original=None signals the verifier to fail SAFE."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_translate = ex.submit(_client.translate_speech, audio)
        f_transcribe = ex.submit(_client.transcribe_speech, audio)
        t = f_translate.result()
        en, lang = t["transcript"], t.get("language_code", "unknown")
        try:
            orig = f_transcribe.result()["transcript"]
        except Exception:
            orig = None     # never silently skip verification; verifier fail-safes
    return en, orig, lang
