"""Vercel serverless entry — exposes the FastAPI ASGI app.

Deployed in mock mode by default: the demo reads model responses from fixtures/,
so it's fast (well under the serverless timeout) and needs no API key. Set
INTAKE_MODE=live + SARVAM_API_KEY in the Vercel project env to call real models
(requires a plan whose function timeout covers the ~25s live pipeline)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("INTAKE_MODE", "mock")

from shuka.server import app  # noqa: E402  (path set above)

# Vercel's @vercel/python detects the ASGI `app` object.
