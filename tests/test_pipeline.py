from pathlib import Path
from shuka.pipeline import run_intake


def test_demo_pipeline_runs_on_fixtures_no_network():
    note, audio = run_intake(Path("samples/complaint_hinglish.wav"))
    assert note.language_detected == "hi-IN"
    assert any(s.name == "fever" and s.status.value == "denied" for s in note.symptoms)
    assert "nahi" in note.verbatim_transcript_original
    assert len(audio) > 0
