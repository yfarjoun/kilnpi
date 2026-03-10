"""Tests for Pydantic DTO models."""

import pytest
from pydantic import ValidationError

from backend.dto import PIDParams, ProgramCreate, Segment, SetpointRequest


def test_segment_valid() -> None:
    seg = Segment(ramp_min=30, soak_min=60, target_temp=500.0)
    assert seg.ramp_min == 30
    assert seg.target_temp == 500.0


def test_segment_ramp_bounds() -> None:
    with pytest.raises(ValidationError):
        Segment(ramp_min=-1, soak_min=0, target_temp=100.0)
    with pytest.raises(ValidationError):
        Segment(ramp_min=2001, soak_min=0, target_temp=100.0)


def test_pid_params_bounds() -> None:
    params = PIDParams(p=100, i=500, d=100, cycle_time=20)
    assert params.p == 100

    # p=0 is valid (controller can return it)
    assert PIDParams(p=0, i=500, d=100, cycle_time=20).p == 0
    with pytest.raises(ValidationError):
        PIDParams(p=100, i=500, d=100, cycle_time=1)


def test_setpoint_request() -> None:
    req = SetpointRequest(value=850.5)
    assert req.value == 850.5


def test_program_create() -> None:
    prog = ProgramCreate(
        name="Test Firing",
        segments=[
            Segment(ramp_min=30, soak_min=60, target_temp=500.0),
            Segment(ramp_min=60, soak_min=120, target_temp=1000.0),
        ],
    )
    assert prog.name == "Test Firing"
    assert len(prog.segments) == 2
