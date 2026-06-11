import pytest
from pathlib import Path
from shuka.config import Settings
from shuka.sarvam import FixtureMissingError, SarvamClient


def _client():
    return SarvamClient(Settings(intake_mode="mock", fixtures_dir=Path("fixtures")))


def test_mock_translate_reads_fixture():
    out = _client().translate_speech(Path("samples/complaint_hinglish.wav"))
    assert "transcript" in out and out["language_code"] == "hi-IN"


def test_mock_transcribe_reads_codemix_fixture():
    out = _client().transcribe_speech(Path("samples/complaint_hinglish.wav"))
    assert "nahi" in out["transcript"]          # the negation survives in the original view


def test_missing_fixture_raises_never_falls_to_live():
    with pytest.raises(FixtureMissingError):
        _client().translate_speech(Path("samples/nonexistent.wav"))


def test_mock_mode_never_imports_sdk(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "sarvamai", None)  # import would explode
    out = _client().translate_speech(Path("samples/complaint_hinglish.wav"))
    assert out["transcript"]
