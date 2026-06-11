from shuka.schema import FactStatus, GapKind, IntakeNote


def render_terminal(note: IntakeNote) -> str:
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("SHUKA PRE-CONSULT NOTE")
    lines.append("=" * 60)
    lines.append(f"Language: {note.language_detected}")
    lines.append(f"Chief Complaint: {note.chief_complaint}")
    lines.append(f'  Patient words: "{note.chief_complaint_patient_words}"')
    lines.append("")

    lines.append("HPI")
    lines.append("-" * 40)
    hpi = note.hpi
    for field in ("onset", "duration", "character", "location",
                  "aggravating", "relieving", "progression"):
        val = getattr(hpi, field)
        if val:
            badge = " [UNCONFIRMED — patient to verify]" if hpi.needs_confirmation.get(field) else ""
            lines.append(f"  {field}: {val}{badge}")
    lines.append("")

    if note.symptoms:
        lines.append("SYMPTOMS")
        lines.append("-" * 40)
        for s in note.symptoms:
            status_badge = "[STATED]" if s.status == FactStatus.STATED else "[DENIED]"
            unconf = " [UNCONFIRMED — patient to verify]" if s.needs_confirmation else ""
            term = f' (patient: "{s.patient_term}")' if s.patient_term else ""
            lines.append(f"  {status_badge} {s.name}{term}{unconf}")
        lines.append("")

    if note.medications:
        lines.append("MEDICATIONS")
        lines.append("-" * 40)
        for m in note.medications:
            unconf = " [UNCONFIRMED]" if m.needs_confirmation else ""
            lines.append(f"  [{m.source.value}] {m.name} conf={m.confidence:.0%}{unconf}")
        lines.append("")

    if note.lab_values:
        lines.append("LAB VALUES")
        lines.append("-" * 40)
        for lab in note.lab_values:
            unconf = " [UNCONFIRMED]" if lab.needs_confirmation else ""
            unit = f" {lab.unit}" if lab.unit else ""
            lines.append(f"  {lab.analyte}: {lab.value}{unit} [doc conf={lab.confidence:.0%}]{unconf}")
        lines.append("")

    if note.gaps:
        lines.append("GAPS / FOLLOW-UPS")
        lines.append("-" * 40)
        by_kind: dict[str, list] = {}
        for gap in note.gaps:
            by_kind.setdefault(gap.kind.value, []).append(gap)
        for kind_val, gaps in by_kind.items():
            lines.append(f"  [{kind_val.upper()}]")
            for gap in gaps:
                lines.append(f"    field: {gap.field}")
                if gap.patient_term:
                    lines.append(f"    patient term: {gap.patient_term}")
                if gap.followup_vernacular:
                    lines.append(f"    follow-up: {gap.followup_vernacular}")
                if gap.followup_options:
                    lines.append(f"    options: {', '.join(gap.followup_options)}")
        lines.append("")

    if note.verification_flags:
        lines.append("VERIFICATION FLAGS")
        lines.append("-" * 40)
        for flag in note.verification_flags:
            lines.append(f"  [{flag.kind.value}] {flag.fact_ref}: {flag.detail}")
            if flag.original_evidence:
                lines.append(f"    evidence: {flag.original_evidence}")
        lines.append("")

    lines.append("VERBATIM TRANSCRIPTS")
    lines.append("-" * 40)
    lines.append(f"  EN:  {note.verbatim_transcript_en}")
    if note.verbatim_transcript_original:
        lines.append(f"  ORI: {note.verbatim_transcript_original}")
    lines.append("=" * 60)

    return "\n".join(lines)
