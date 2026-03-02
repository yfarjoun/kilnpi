"""Pydantic models for API request/response."""

from pydantic import BaseModel, Field


class Segment(BaseModel):
    ramp_min: int = Field(ge=0, le=2000, description="Ramp time in minutes (0=end, 2000=skip)")
    soak_min: int = Field(ge=0, le=9999, description="Soak time in minutes (0=skip soak)")
    target_temp: float = Field(description="Target temperature for this segment")


class PIDParams(BaseModel):
    p: int = Field(ge=1, le=9999, description="Proportional band")
    i: int = Field(ge=0, le=3000, description="Integral time")
    d: int = Field(ge=0, le=2000, description="Derivative time (seconds)")
    cycle_time: int = Field(ge=2, le=120, description="Control cycle time (seconds)")


class StatusResponse(BaseModel):
    pv: float
    sp: float
    mv: float
    run_mode: str
    segment: int
    segment_elapsed_min: int
    alarm: bool
    timestamp: str


class SetpointRequest(BaseModel):
    value: float


class ProgramCreate(BaseModel):
    name: str
    description: str | None = None
    segments: list[Segment]


class ProgramUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    segments: list[Segment] | None = None


class ProgramResponse(BaseModel):
    id: int
    name: str
    description: str | None
    segments: list[Segment]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class FiringResponse(BaseModel):
    id: int
    program_id: int | None
    program_name: str | None
    started_at: str
    ended_at: str | None
    status: str
    notes: str | None

    model_config = {"from_attributes": True}


class ReadingResponse(BaseModel):
    timestamp: str
    pv: float
    sp: float
    mv: float
    segment: int | None

    model_config = {"from_attributes": True}


class FiringDetailResponse(BaseModel):
    firing: FiringResponse
    readings: list[ReadingResponse]


class AutotuneRequest(BaseModel):
    start: bool = True
