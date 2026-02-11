from pydantic import BaseModel, Field
from typing import Optional


class PersonIdentifiers(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    city: Optional[str] = None
    linkedin: Optional[str] = None
    telegram: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class ExtractedPerson(BaseModel):
    temp_id: str
    name: str
    name_variations: list[str] = Field(default_factory=list)
    identifiers: PersonIdentifiers = Field(default_factory=PersonIdentifiers)


class ExtractedAssertion(BaseModel):
    subject: str  # temp_id of person
    predicate: str
    value: str
    confidence: float = 0.5


class ExtractedEdge(BaseModel):
    source: str  # temp_id
    target: str  # temp_id
    type: str
    context: Optional[str] = None


class ExtractionResult(BaseModel):
    people: list[ExtractedPerson] = Field(default_factory=list)
    assertions: list[ExtractedAssertion] = Field(default_factory=list)
    edges: list[ExtractedEdge] = Field(default_factory=list)


# API Request/Response models

class ProcessVoiceRequest(BaseModel):
    storage_path: str = Field(..., description="Path to audio file in voice-notes bucket")


class ProcessTextRequest(BaseModel):
    text: str = Field(..., description="Text note content")


class ProcessResponse(BaseModel):
    evidence_id: str
    status: str = "processing"
    message: str = "Processing started"


class EvidenceStatus(BaseModel):
    evidence_id: str
    status: str
    processed: bool
    error_message: Optional[str] = None
    people_count: Optional[int] = None
    assertions_count: Optional[int] = None
