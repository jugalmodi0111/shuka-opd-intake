import base64
from fastapi.testclient import TestClient
from shuka.server import app

client = TestClient(app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "shuka" in r.text.lower() or "Shuka" in r.text


def test_list_samples():
    r = client.get("/samples")
    assert r.status_code == 200
    samples = r.json()["samples"]
    assert any("hinglish" in s for s in samples)


def test_get_sample_bytes():
    r = client.get("/samples/complaint_hinglish.wav")
    assert r.status_code == 200
    assert len(r.content) > 0


def test_get_sample_404():
    r = client.get("/samples/nonexistent.wav")
    assert r.status_code == 404


def test_intake_end_to_end_mock():
    # Upload the hinglish sample; mock fixtures must resolve via stem
    with open("samples/complaint_hinglish.wav", "rb") as f:
        r = client.post("/intake", files={"audio": ("complaint_hinglish.wav", f, "audio/wav")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "note" in data
    assert data["note"]["chief_complaint"]
    assert "readback_wav_b64" in data
    # base64 decodes cleanly
    base64.b64decode(data["readback_wav_b64"])
