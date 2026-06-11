"""Convert EN transcript to schema-valid IntakeNote via Sarvam-M with repair loop."""
from __future__ import annotations

import json
import re

from shuka.schema import IntakeNote

SYSTEM_PROMPT = """\
You convert a patient's spoken English transcript into a structured medical intake note.
Output ONE JSON object that EXACTLY matches this schema. No prose, no markdown fences.

SCHEMA (exact keys — do not rename, do not invent keys):
{
  "language_detected": "<bcp47 like hi-IN>",
  "chief_complaint": "<short English summary of the main problem>",
  "chief_complaint_patient_words": "<the patient's own words for it>",
  "hpi": {
    "onset": null, "duration": "<e.g. 2 days or null>", "character": null,
    "location": null, "aggravating": null, "relieving": null, "progression": null
  },
  "symptoms": [
    {
      "name": "<clinical name>",
      "patient_term": "<patient's word or null>",
      "status": "stated" | "denied",
      "needs_confirmation": false,
      "provenance": {"source": "spoken", "transcript_span": "<exact quote>", "confidence": 0.9}
    }
  ],
  "medications": [
    {"name": "<drug>", "patient_term": "<patient word>", "dose": null, "frequency": null,
     "needs_confirmation": true,
     "provenance": {"source": "spoken", "transcript_span": "<quote>", "confidence": 0.8}}
  ],
  "verbatim_transcript_en": "<the full transcript verbatim>"
}

HARD RULES (faithfulness contract):
1. Capture ONLY facts explicitly stated. NEVER infer, assume, or synthesize.
2. "status" is exactly "stated" (present) or "denied" (patient said they do NOT have it).
3. Every symptom and medication MUST include a "provenance" object with source="spoken",
   a "transcript_span" quoting the words, and a confidence 0..1.
4. Do NOT use status "not_mentioned" — omit anything not mentioned.
5. "provenance.source" is the literal string "spoken" (or "document"); never free text.
6. Output valid JSON only — start with { and end with }."""

_chat_ref: str = ""


def _extract_json(raw: str) -> str:
    """Pull the first balanced JSON object out of a model reply.

    Tolerates ```json fences, leading prose, and trailing commentary by scanning
    for the first '{' and its matching '}' (brace-depth aware, string-aware)."""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    start = s.find("{")
    if start < 0:
        return s
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return _strip_trailing_commas(s[start:i + 1])
    return _strip_trailing_commas(s[start:])


def _strip_trailing_commas(s: str) -> str:
    """Remove trailing commas before } or ] — a common LLM JSON defect."""
    return re.sub(r",(\s*[}\]])", r"\1", s)


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

    import time

    last_err: Exception | None = None
    for _attempt in range(4):
        raw = _chat(messages)
        if not (raw or "").strip():
            # Empty response — transient (rate limit / reasoning-only). Back off and retry
            # the SAME prompt rather than appending an empty turn that poisons context.
            last_err = ValueError("empty model response")
            time.sleep(1.5 * (_attempt + 1))
            continue
        try:
            data = json.loads(_extract_json(raw))
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
        f"structure.build_note failed after 4 attempts: {last_err}"
    )
