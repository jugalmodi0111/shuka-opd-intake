"""Convert EN transcript to schema-valid IntakeNote via Sarvam-M with repair loop."""
from __future__ import annotations

import json
import re

from shuka.schema import IntakeNote

SYSTEM_PROMPT = """\
You convert a patient's spoken English transcript into a structured medical intake note.

FAITHFULNESS CONTRACT (HARD RULES):
1. Capture ONLY facts explicitly stated in the transcript.
2. NEVER infer, assume, or synthesize clinical facts.
3. Denied symptoms → status="denied" with provenance evidence.
4. Uncertain facts → needs_confirmation=True.
5. Do NOT add any symptom, diagnosis, or condition not in the transcript.
6. Do NOT use "not_mentioned" as a status — omit symptoms entirely if not mentioned.

OUTPUT: Valid JSON matching the IntakeNote Pydantic schema.
No prose, no markdown fences, no explanation — JSON only."""

_chat_ref: str = ""


def _chat(messages: list) -> str:
    """Thin seam: swappable in tests via monkeypatch.setattr(structure, '_chat', ...)."""
    from shuka import sarvam as _s
    return _s._client.chat(messages, stage="structure", ref=_chat_ref)


def build_note(transcript_en: str, lang: str, ref: str) -> IntakeNote:
    """Build IntakeNote with up to 3-attempt repair loop."""
    global _chat_ref
    _chat_ref = ref

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Patient language detected: {lang}\n"
                f"Transcript (English):\n{transcript_en}"
            ),
        },
    ]

    last_err: Exception | None = None
    for _attempt in range(3):
        raw = _chat(messages)
        # Strip markdown fences if model adds them
        clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        clean = re.sub(r"\s*```$", "", clean.strip())
        try:
            data = json.loads(clean)
            note = IntakeNote.model_validate(data)
            note.verbatim_transcript_en = transcript_en
            return note
        except Exception as exc:
            last_err = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Validation error: {exc}\n"
                        "Return corrected JSON only — no prose, no fences."
                    ),
                }
            )

    raise RuntimeError(
        f"structure.build_note failed after 3 repair attempts: {last_err}"
    )
