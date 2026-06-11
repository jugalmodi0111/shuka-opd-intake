"""Force MOCK mode for the whole suite, regardless of what .env says.

The repo's .env may be set to INTAKE_MODE=live for manual live testing. Tests
must stay deterministic and never hit the network, so every module-level
SarvamClient singleton is pinned to mock before each test. Tests that explicitly
want a live client construct their own SarvamClient(Settings(intake_mode="live")).
"""
import pytest


@pytest.fixture(autouse=True)
def _force_mock_mode():
    from shuka import asr, readback, sarvam
    for mod in (sarvam, asr, readback):
        client = getattr(mod, "_client", None)
        if client is not None:
            client.mode = "mock"
    yield
