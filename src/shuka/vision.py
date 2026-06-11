"""Vision gate: prescription/document reading with non-diagnostic enforcement."""
from __future__ import annotations

from pathlib import Path

from shuka.schema import DocumentRead

# Allowlist of every prompt this module may send to the VLM.
# The prompt-allowlist spy test asserts ONLY prompts in this set are used.
ALLOWED_PROMPTS: frozenset[str] = frozenset({
    "Is this a medical prescription or lab report? Answer: prescription | lab_report | other",
    "Extract all medications from this prescription. Return JSON: "
    '{"medications": [{"name": "...", "dose": "...", "frequency": "..."}]}. '
    "Unknown fields → null. No inference.",
    "Extract all lab results from this report. Return JSON: "
    '{"labs": [{"name": "...", "value": "...", "unit": "...", "flag": "...", "reference": "..."}]}. '
    "Unknown fields → null. No inference.",
})

_CLASSIFY_PROMPT = "Is this a medical prescription or lab report? Answer: prescription | lab_report | other"
_RX_PROMPT = (
    "Extract all medications from this prescription. Return JSON: "
    '{"medications": [{"name": "...", "dose": "...", "frequency": "..."}]}. '
    "Unknown fields → null. No inference."
)
_LAB_PROMPT = (
    "Extract all lab results from this report. Return JSON: "
    '{"labs": [{"name": "...", "value": "...", "unit": "...", "flag": "...", "reference": "..."}]}. '
    "Unknown fields → null. No inference."
)

# Ensure every prompt used above is in ALLOWED_PROMPTS (fail at import time if not)
assert _CLASSIFY_PROMPT in ALLOWED_PROMPTS
assert _RX_PROMPT in ALLOWED_PROMPTS
assert _LAB_PROMPT in ALLOWED_PROMPTS


def read_document(image_path: Path) -> DocumentRead:
    """Classify image then extract structured data. Non-diagnostic: never interprets findings."""
    import json
    from shuka import sarvam as _s

    doc_type = _s._client.classify_image(image_path, _CLASSIFY_PROMPT).strip().lower()

    if doc_type == "prescription":
        raw = _s._client.extract_markdown(image_path, _RX_PROMPT)
        data = json.loads(raw)
        return DocumentRead(
            doc_type="prescription",
            raw_text=raw,
            medications=data.get("medications", []),
            labs=[],
        )
    elif doc_type == "lab_report":
        raw = _s._client.extract_markdown(image_path, _LAB_PROMPT)
        data = json.loads(raw)
        return DocumentRead(
            doc_type="lab_report",
            raw_text=raw,
            medications=[],
            labs=data.get("labs", []),
        )
    else:
        return DocumentRead(doc_type="other", raw_text="", medications=[], labs=[])
