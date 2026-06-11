from pathlib import Path
from shuka import asr, readback, structure
from shuka.schema import IntakeNote


def run_intake(audio: Path, image: Path | None = None) -> tuple[IntakeNote, bytes]:
    ref = audio.stem
    en, orig, lang = asr.transcribe_both(audio)
    note = structure.build_note(en, lang, ref)
    note.verbatim_transcript_original = orig
    # Task 8 inserts: verify.cross_check / verify.verify_facts around this point
    # Task 17 inserts: vision + merge when image is provided
    # Task 14 inserts: gaps.detect_gaps on the ORIGINAL transcript
    audio_out = readback.build(note, lang, ref)
    return note, audio_out
