from shuka.config import settings
from shuka.sarvam import SarvamClient
from shuka.schema import IntakeNote

_client = SarvamClient(settings)


def build(note: IntakeNote, lang: str, ref: str) -> bytes:
    text = summary_text(note, lang)
    return _client.tts(text, lang, ref)


def summary_text(note: IntakeNote, lang: str) -> str:
    return note.chief_complaint    # placeholder; Task 18 replaces with 4-part templates
