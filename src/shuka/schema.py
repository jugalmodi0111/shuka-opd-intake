from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class FactStatus(str, Enum):
    STATED = "stated"
    DENIED = "denied"
    NOT_MENTIONED = "not_mentioned"


class Source(str, Enum):
    SPOKEN = "spoken"
    DOCUMENT = "document"


class DriftKind(str, Enum):
    NEGATION = "negation_drift"
    LATERALITY = "laterality_drift"
    NUMBER = "number_drift"
    UNVERIFIED = "unverified"


class GapKind(str, Enum):
    HPI_DIMENSION = "hpi_dimension"
    LEXICAL_COLLAPSE = "lexical_collapse"
    TEMPORAL_ANCHOR = "temporal_anchor"
    CATEGORY_DENIAL = "category_denial"
    FREQUENCY_DROP = "frequency_drop"
    REGISTER_AMBIG = "register_ambiguity"


class Provenance(BaseModel):
    source: Source
    transcript_span: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    original_phrase: Optional[str] = None
    confidence: float = Field(ge=0, le=1)


class VerificationFlag(BaseModel):
    fact_ref: str
    kind: DriftKind
    detail: str
    original_evidence: Optional[str] = None


class Symptom(BaseModel):
    name: str
    patient_term: Optional[str] = None
    status: FactStatus
    register: Optional[Literal["experiential", "borrowed_biomedical"]] = None
    needs_confirmation: bool = False
    provenance: Optional[Provenance] = None

    @model_validator(mode="after")
    def _provenance_required(self) -> "Symptom":
        if self.status != FactStatus.NOT_MENTIONED and self.provenance is None:
            raise ValueError(f"symptom {self.name!r}: status {self.status} requires provenance")
        return self


class HPI(BaseModel):
    onset: Optional[str] = None
    duration: Optional[str] = None
    character: Optional[str] = None
    location: Optional[str] = None
    aggravating: Optional[str] = None
    relieving: Optional[str] = None
    progression: Optional[str] = None
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    needs_confirmation: dict[str, bool] = Field(default_factory=dict)


class Medication(BaseModel):
    name: str
    patient_term: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    source: Optional[Source] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    register: Optional[Literal["experiential", "borrowed_biomedical"]] = None
    needs_confirmation: bool = False
    provenance: Optional[Provenance] = None


class LabValue(BaseModel):
    analyte: str
    value: str
    unit: Optional[str] = None
    measured_on: Optional[str] = None
    source: Source = Source.DOCUMENT
    confidence: float = Field(ge=0, le=1)
    needs_confirmation: bool = False


class Lab(BaseModel):
    name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    flag: Optional[str] = None
    reference: Optional[str] = None
    provenance: Optional[Provenance] = None


class DocumentRead(BaseModel):
    doc_type: str  # "prescription" | "lab_report" | "other"
    raw_text: str
    medications: list[dict] = Field(default_factory=list)
    labs: list[dict] = Field(default_factory=list)


class Gap(BaseModel):
    field: str
    kind: GapKind = GapKind.HPI_DIMENSION
    reason: str = "not stated by patient"
    patient_term: Optional[str] = None
    source_stream: Literal["original", "english"] = "original"
    followup_vernacular: Optional[str] = None
    followup_options: list[str] = Field(default_factory=list)
    resolution_candidate: Optional[str] = None
    patient_response_verbatim: Optional[str] = None
    leads_diagnosis: bool = False

    @field_validator("leads_diagnosis")
    @classmethod
    def _never_leading(cls, v: bool) -> bool:
        # Forward-defense: template-authored follow-ups cannot set this flag.
        # It becomes load-bearing on the LLM fallback path (Task 14b: probes for
        # collapse terms not in the lexicon) and on any externally-constructed
        # Gap. The active enforcement layer for pre-authored follow-ups is
        # gaps.assert_non_leading, which runs at detection time.
        if v:
            raise ValueError(
                "leading follow-up: generator attempted to introduce an unstated "
                "symptom/condition; this is forbidden by the non-leading boundary"
            )
        return v


class IntakeNote(BaseModel):
    language_detected: str
    chief_complaint: str
    chief_complaint_patient_words: str
    hpi: HPI
    symptoms: list[Symptom] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    lab_values: list[LabValue] = Field(default_factory=list)
    labs: list[Lab] = Field(default_factory=list)
    allergies: list[Symptom] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    verification_flags: list[VerificationFlag] = Field(default_factory=list)
    verbatim_transcript_en: str
    verbatim_transcript_original: Optional[str] = None
    unread_documents: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _invariants(self) -> "IntakeNote":
        for s in self.symptoms:
            if s.status == FactStatus.NOT_MENTIONED:
                raise ValueError("not_mentioned symptoms must be Gaps, not emitted symptoms")
        flagged = {f.fact_ref for f in self.verification_flags}
        confirm_refs = {s.name for s in self.symptoms if s.needs_confirmation}
        confirm_refs |= {f"hpi.{k}" for k, v in self.hpi.needs_confirmation.items() if v}
        confirm_refs |= {m.name for m in self.medications if m.needs_confirmation}
        for ref in flagged:
            if ref not in confirm_refs:
                raise ValueError(f"VerificationFlag {ref!r} has no fact carrying needs_confirmation")
        return self
