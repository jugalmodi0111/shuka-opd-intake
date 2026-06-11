from pathlib import Path
from shuka import asr, readback, structure
from shuka.config import settings
from shuka.gaps import Lexicons, detect_gaps
from shuka.schema import IntakeNote

_LEX = Lexicons.load(settings.lexicon_dir)


def run_intake(audio: Path, image: Path | None = None) -> tuple[IntakeNote, bytes]:
    ref = audio.stem
    en, orig, lang = asr.transcribe_both(audio)

    # CORE #1 — verifier: cross-check the two ASR views, mark drifted facts
    from shuka import verify
    report = verify.cross_check(
        verify.detect_cues(orig, lang) if orig else None,
        verify.detect_cues(en, "en"))
    note = structure.build_note(en, lang, ref)
    note.verbatim_transcript_original = orig
    note = verify.verify_facts(note, report, en, orig)

    # Vision: read prescription/lab document and merge (provenance-preserving)
    if image is not None:
        from shuka import merge, vision
        doc = vision.read_document(image)
        note = merge.merge_document(note, doc)

    # CORE #2 — gap engine: runs on the ORIGINAL (codemix) transcript only
    note.gaps = detect_gaps(note, orig, lang, _LEX, settings.encounter_date)

    audio_out = readback.build(note, lang, ref)
    return note, audio_out
