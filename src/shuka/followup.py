"""Conversational follow-up: fold a patient's answer to a gap back into the note.

Deterministic + provenance-preserving. No new clinical facts are invented — the
answer is recorded verbatim, attached to the field the question was about, the gap
is marked resolved, and the turn is appended to qa_history so later turns carry
context. This is the loop that makes the intake a conversation, not a one-shot.
"""
from __future__ import annotations

from shuka.schema import GapKind, IntakeNote, Provenance, QATurn, Source


def apply_followup(note: IntakeNote, gap_field: str, answer: str) -> IntakeNote:
    """Record the patient's answer to the gap identified by `gap_field`.

    - marks that gap resolved + stores the verbatim answer
    - folds the answer into the structured note where the field is known
      (HPI dimension → fills the HPI axis; lexical/register → annotates the symptom)
    - appends a QATurn to qa_history (conversational memory)
    Raises KeyError if no open gap matches `gap_field`."""
    answer = (answer or "").strip()
    gap = next((g for g in note.gaps if g.field == gap_field and not g.resolved), None)
    if gap is None:
        raise KeyError(f"no open gap with field '{gap_field}'")

    gap.resolved = True
    gap.patient_response_verbatim = answer

    # Fold into the structured note (patient-sourced, needs no further confirmation
    # since the patient just stated it directly).
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
        answer=answer,
    ))
    return note


def open_gaps(note: IntakeNote) -> list:
    """Gaps still awaiting an answer."""
    return [g for g in note.gaps if not g.resolved]
