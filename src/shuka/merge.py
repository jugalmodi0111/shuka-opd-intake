"""Merge DocumentRead findings into IntakeNote — provenance-preserving, non-overwriting."""
from __future__ import annotations

from shuka.schema import DocumentRead, IntakeNote, Medication, Lab, Provenance, Source


def merge_document(note: IntakeNote, doc: DocumentRead) -> IntakeNote:
    """Add document-sourced medications/labs to note. Never overwrites spoken facts.
    Medications already present (name match) get needs_confirmation=True if values differ."""
    from shuka.schema import FactStatus

    # Medications
    existing_names = {m.name.lower(): i for i, m in enumerate(note.medications)}
    for raw_med in doc.medications:
        name = (raw_med.get("name") or "").strip()
        if not name:
            continue
        prov = Provenance(source=Source.DOCUMENT, transcript_span=name, confidence=0.80)
        med = Medication(
            name=name,
            patient_term=name,
            dose=raw_med.get("dose"),
            frequency=raw_med.get("frequency"),
            needs_confirmation=True,  # always confirm document-sourced meds
            provenance=prov,
        )
        key = name.lower()
        if key in existing_names:
            # Already in note from voice — mark for confirmation if dose differs
            existing = note.medications[existing_names[key]]
            if existing.dose != med.dose:
                existing.needs_confirmation = True
        else:
            note.medications.append(med)

    # Labs
    for raw_lab in doc.labs:
        name = (raw_lab.get("name") or "").strip()
        if not name:
            continue
        prov = Provenance(source=Source.DOCUMENT, transcript_span=name, confidence=0.80)
        lab = Lab(
            name=name,
            value=raw_lab.get("value"),
            unit=raw_lab.get("unit"),
            flag=raw_lab.get("flag"),
            reference=raw_lab.get("reference"),
            provenance=prov,
        )
        note.labs.append(lab)

    return note
