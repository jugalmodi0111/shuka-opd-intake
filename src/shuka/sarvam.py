import json
import time
from pathlib import Path
from shuka.config import Settings, settings as _settings


class FixtureMissingError(RuntimeError):
    """Mock mode never falls back to live. A missing fixture is a loud error."""


# Map detected/transcript languages to Bulbul target codes; default hi-IN.
_TTS_LANG = {
    "hi": "hi-IN", "hi-in": "hi-IN", "ta": "ta-IN", "ta-in": "ta-IN",
    "bn": "bn-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN",
    "mr": "mr-IN", "gu": "gu-IN", "pa": "pa-IN", "od": "od-IN", "en": "en-IN",
}
# Valid bulbul:v3 speakers (anushka/vidya are v2-only).
_TTS_SPEAKER = {"hi-IN": "priya", "ta-IN": "kavitha", "en-IN": "priya"}
_TTS_DEFAULT_SPEAKER = "priya"


class SarvamClient:
    # SDK signatures verified against installed sarvamai==0.1.28:
    #   SarvamAI(api_subscription_key=...)
    #   speech_to_text.transcribe(file=, model='saaras:v3', mode=, language_code=)
    #       -> .transcript / .language_code   (mode='translate' → EN, 'codemix' → original)
    #   chat.completions(messages=, model='sarvam-m') -> .choices[0].message.content
    #   text_to_speech.convert(text=, target_language_code=, model=, output_audio_codec='wav')
    #       -> .audios[0]  (base64 string)
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mode = settings.intake_mode
        self._sdk = None  # lazy SarvamAI client (live only)

    def _client_sdk(self):
        if self._sdk is None:
            from sarvamai import SarvamAI
            self._sdk = SarvamAI(api_subscription_key=self.settings.sarvam_api_key)
        return self._sdk

    def _fixture_json(self, stem: str, stage: str) -> dict:
        p = self.settings.fixtures_dir / f"{stem}.{stage}.json"
        if not p.exists():
            raise FixtureMissingError(f"missing fixture {p}; mock mode never calls live APIs")
        return json.loads(p.read_text())

    def _log(self, stage: str, ref: str, t0: float) -> None:
        Path("logs").mkdir(exist_ok=True)
        rec = {"stage": stage, "model": "mock" if self.mode == "mock" else stage,
               "input_ref": ref, "latency_ms": int((time.time() - t0) * 1000),
               "mode": self.mode}
        with open("logs/calls.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")

    def translate_speech(self, audio_path: Path) -> dict:
        """English witness — saaras:v3 in translate mode."""
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(audio_path.stem, "translate")
            stt = self._client_sdk().speech_to_text
            with open(audio_path, "rb") as f:
                r = stt.transcribe(file=f, model=self.settings.asr_model, mode="translate")
            return {"transcript": r.transcript,
                    "language_code": getattr(r, "language_code", "unknown") or "unknown"}
        finally:
            self._log("asr.translate", str(audio_path), t0)

    def transcribe_speech(self, audio_path: Path) -> dict:
        """Original codemix witness — saaras:v3 in codemix mode (preserves patient words)."""
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(audio_path.stem, "transcribe")
            stt = self._client_sdk().speech_to_text
            with open(audio_path, "rb") as f:
                r = stt.transcribe(file=f, model=self.settings.asr_model,
                                   mode="codemix", language_code="unknown")
            return {"transcript": r.transcript}
        finally:
            self._log("asr.transcribe", str(audio_path), t0)

    def chat(self, messages: list[dict], stage: str, ref: str) -> str:
        t0 = time.time()
        try:
            if self.mode == "mock":
                return json.dumps(self._fixture_json(ref, stage))
            resp = self._client_sdk().chat.completions(
                messages=messages, model=self.settings.llm_model, temperature=0.2)
            return resp.choices[0].message.content or ""
        finally:
            self._log(f"llm.{stage}", ref, t0)

    def classify_image(self, image_path: Path, prompt: str) -> str:
        # prompt is explicit (not internal) so Task 16's allowlist spy can
        # assert at this seam; mock ignores it but the signature is final now
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(image_path.stem, "vision_gate")["label"]
            # Live document vision uses the async document_intelligence job API
            # (initialise → start → poll → download). Not wired for the synchronous
            # demo path; document-read is an optional pipeline branch.
            raise NotImplementedError(
                "live vision not wired — use mock fixtures, or implement the "
                "document_intelligence job flow (initialise/start/get_status/get_download_links)")
        finally:
            self._log("vision.gate", str(image_path), t0)

    def extract_markdown(self, image_path: Path, prompt: str) -> str:
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(image_path.stem, "vision_extract")["markdown"]
            raise NotImplementedError(
                "live vision not wired — see classify_image; document-read is optional")
        finally:
            self._log("vision.extract", str(image_path), t0)

    def tts(self, text: str, lang: str, ref: str) -> bytes:
        t0 = time.time()
        try:
            if self.mode == "mock":
                p = self.settings.fixtures_dir / f"{ref}.readback.wav"
                if not p.exists():
                    raise FixtureMissingError(f"missing fixture {p}")
                return p.read_bytes()
            import base64
            target = _TTS_LANG.get((lang or "hi").lower().split("-")[0], "hi-IN")
            r = self._client_sdk().text_to_speech.convert(
                text=text[:1500],  # Bulbul per-call text limit guard
                target_language_code=target,
                speaker=_TTS_SPEAKER.get(target, _TTS_DEFAULT_SPEAKER),
                model=self.settings.tts_model,
                output_audio_codec="wav",
            )
            return base64.b64decode(r.audios[0])
        finally:
            self._log("tts", ref, t0)


_client: SarvamClient = SarvamClient(_settings)
