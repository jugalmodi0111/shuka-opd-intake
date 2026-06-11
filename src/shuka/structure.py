import json
from pathlib import Path
from shuka.config import settings
from shuka.sarvam import SarvamClient
from shuka.schema import IntakeNote

_client = SarvamClient(settings)


def build_note(transcript_en: str, lang: str, ref: str) -> IntakeNote:
    raw = _client.chat(messages=_messages(transcript_en), stage="structure", ref=ref)
    return IntakeNote(**json.loads(raw))


def _messages(transcript_en: str) -> list[dict]:
    return [{"role": "user", "content": transcript_en}]   # real prompt: Task 15
