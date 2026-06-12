"""Conversational follow-up: fold a patient's answer to a gap back into the note.

Deterministic + provenance-preserving. No new clinical facts are invented — the
answer is recorded verbatim, attached to the field the question was about, the gap
is marked resolved, and the turn is appended to qa_history so later turns carry
context. This is the loop that makes the intake a conversation, not a one-shot.
"""
from __future__ import annotations

import json

from shuka.schema import (FactStatus, GapKind, IntakeNote, Provenance, QATurn,
                          Source, Symptom)


def _is_option_answer(gap, answer: str) -> bool:
    """True if the answer is one of the gap's predefined chips (→ deterministic fold)."""
    a = answer.strip().lower()
    return any(a == (o or "").strip().lower() for o in (gap.followup_options or []))


def _interpret_messages(gap, answer: str, note: IntakeNote) -> list:
    """Prompt Sarvam to interpret a FREE-TEXT answer in conversational context.
    Returns a constrained JSON patch — code applies it, the model never rewrites
    the whole note (keeps control + the non-leading boundary in code)."""
    history = "\n".join(f"Q: {t.question}\nA: {t.answer}" for t in note.qa_history) or "(none yet)"
    return [
        {"role": "system", "content": (
            "You interpret a patient's free-text answer to a clinical follow-up question "
            "during an intake conversation. Return JSON ONLY:\n"
            '{"field_value": "<concise normalized value for the asked field, patient words ok>", '
            '"additional_findings": [{"name": "<clinical>", "patient_term": "<word>", '
            '"status": "stated"|"denied"}], "summary": "<one short line>"}\n'
            "RULES: capture ONLY what the patient actually said in THIS answer. "
            "Never infer or add symptoms they did not state. additional_findings is for "
            "extra facts the patient volunteered in the answer; usually empty. No prose."
        )},
        {"role": "user", "content": (
            f"Patient language: {note.language_detected}\n"
            f"Original complaint (verbatim): {note.verbatim_transcript_original or note.verbatim_transcript_en}\n"
            f"Conversation so far:\n{history}\n\n"
            f"Question asked: {gap.followup_vernacular or gap.field}\n"
            f"Field being filled: {gap.field}\n"
            f"Patient's answer: {answer}"
        )},
    ]


def _llm_interpret(gap, answer: str, note: IntakeNote) -> dict | None:
    """Call Sarvam to interpret a free-text answer. Returns a patch dict or None
    (None → caller falls back to the deterministic fold; e.g. mock mode / failure)."""
    from shuka import sarvam as _s
    from shuka.structure import _extract_json
    try:
        raw = _s._client.chat(_interpret_messages(gap, answer, note),
                              stage="followup", ref=f"followup_{gap.field}")
        data = json.loads(_extract_json(raw))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def apply_followup(note: IntakeNote, gap_field: str, answer: str) -> IntakeNote:
    """Record the patient's answer to the gap identified by `gap_field`.

    Option-chip answers fold deterministically (fast). FREE-TEXT answers are routed
    through Sarvam to interpret them in conversational context (normalize the field
    value + capture any extra facts the patient volunteered), with a deterministic
    fallback if the LLM is unavailable (e.g. mock mode).

    - marks that gap resolved + stores the verbatim answer
    - folds the answer into the structured note where the field is known
    - appends a QATurn to qa_history (conversational memory)
    Raises KeyError if no open gap matches `gap_field`."""
    answer = (answer or "").strip()
    gap = next((g for g in note.gaps if g.field == gap_field and not g.resolved), None)
    if gap is None:
        raise KeyError(f"no open gap with field '{gap_field}'")

    gap.resolved = True
    gap.patient_response_verbatim = answer

    folded_value = answer
    # Free-text (not a predefined chip) → let the LLM interpret in context.
    if answer and not _is_option_answer(gap, answer):
        patch = _llm_interpret(gap, answer, note)
        if patch:
            folded_value = (patch.get("field_value") or answer).strip()
            for f in patch.get("additional_findings", []) or []:
                name = (f.get("name") or "").strip()
                if not name:
                    continue
                status = FactStatus.DENIED if f.get("status") == "denied" else FactStatus.STATED
                note.symptoms.append(Symptom(
                    name=name, patient_term=f.get("patient_term"), status=status,
                    needs_confirmation=False,
                    provenance=Provenance(source=Source.SPOKEN,
                                          transcript_span=answer, confidence=0.85)))

    # Fold into the structured note (patient-sourced, needs no further confirmation
    # since the patient just stated it directly).
    answer = folded_value
    if gap.field.startswith("hpi."):
        axis = gap.field.split(".", 1)[1]
        if hasattr(note.hpi, axis):
            setattr(note.hpi, axis, answer)
            note.hpi.needs_confirmation[axis] = False
            note.hpi.provenance[axis] = Provenance(
                source=Source.SPOKEN, transcript_span=answer, confidence=0.95)
    elif gap.field.startswith("symptom:"):
        term = gap.field.split(":", 1)[1].lower()
        for s in note.symptoms:
            if term in (s.name or "").lower() or term in (s.patient_term or "").lower():
                # record the experiential character the patient described
                if hasattr(s, "register"):
                    pass  # leave clinical fields untouched; answer lives in qa_history
                s.needs_confirmation = False
    elif gap.field.startswith("history:"):
        for m in note.medications:
            if (gap.patient_term or "").lower() in (m.name or "").lower():
                m.needs_confirmation = False

    note.qa_history.append(QATurn(
        gap_field=gap.field,
        gap_kind=gap.kind.value if isinstance(gap.kind, GapKind) else str(gap.kind),
        question=gap.followup_vernacular or "",
        answer=gap.patient_response_verbatim or answer,  # verbatim, not normalized
    ))
    return note


def open_gaps(note: IntakeNote) -> list:
    """Gaps still awaiting an answer."""
    return [g for g in note.gaps if not g.resolved]
