import json
import time
from pathlib import Path
from shuka.config import Settings


class FixtureMissingError(RuntimeError):
    """Mock mode never falls back to live. A missing fixture is a loud error."""


class SarvamClient:
    # CONFIRMED SDK SIGNATURES (fill from `npx skills add sarvamai/skills` +
    # https://docs.sarvam.ai/llms.txt before writing any live branch):
    #   speech_to_text.translate(...)   -> param names: TODO-verify
    #   speech_to_text.transcribe(...)  -> param names: TODO-verify
    #   text_to_speech.convert(...)     -> param names: TODO-verify
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mode = settings.intake_mode

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
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(audio_path.stem, "translate")
            raise NotImplementedError("live ASR lands in Task 5")
        finally:
            self._log("asr.translate", str(audio_path), t0)

    def transcribe_speech(self, audio_path: Path) -> dict:
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(audio_path.stem, "transcribe")
            raise NotImplementedError("live ASR lands in Task 5")
        finally:
            self._log("asr.transcribe", str(audio_path), t0)

    def chat(self, messages: list[dict], stage: str, ref: str) -> str:
        t0 = time.time()
        try:
            if self.mode == "mock":
                return json.dumps(self._fixture_json(ref, stage))
            raise NotImplementedError("live LLM lands in Task 15")
        finally:
            self._log(f"llm.{stage}", ref, t0)

    def classify_image(self, image_path: Path, prompt: str) -> str:
        # prompt is explicit (not internal) so Task 16's allowlist spy can
        # assert at this seam; mock ignores it but the signature is final now
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(image_path.stem, "vision_gate")["label"]
            raise NotImplementedError("live vision lands in Task 16")
        finally:
            self._log("vision.gate", str(image_path), t0)

    def extract_markdown(self, image_path: Path, prompt: str) -> str:
        t0 = time.time()
        try:
            if self.mode == "mock":
                return self._fixture_json(image_path.stem, "vision_extract")["markdown"]
            raise NotImplementedError("live vision lands in Task 16")
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
            raise NotImplementedError("live TTS lands in Task 18")
        finally:
            self._log("tts", ref, t0)
