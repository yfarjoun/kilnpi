"""Controller interface protocol and base types."""

from typing import Protocol, runtime_checkable

from backend.dto import PIDParams, Segment
from backend.modbus.registers import RunMode


@runtime_checkable
class ControllerInterface(Protocol):
    """Protocol defining the interface for communicating with the kiln controller."""

    def read_pv(self) -> float:
        """Read the current process value (temperature in °C)."""
        ...

    def read_sp(self) -> float:
        """Read the current setpoint."""
        ...

    def read_mv(self) -> float:
        """Read the manipulated variable (output %)."""
        ...

    def write_sp(self, value: float) -> None:
        """Write a new setpoint temperature."""
        ...

    def read_pid(self) -> PIDParams:
        """Read current PID parameters."""
        ...

    def write_pid(self, params: PIDParams) -> None:
        """Write PID parameters to the controller."""
        ...

    def read_program(self) -> list[Segment]:
        """Read the ramp/soak program from the controller."""
        ...

    def write_program(self, segments: list[Segment]) -> None:
        """Write a ramp/soak program to the controller."""
        ...

    def start_program(self) -> None:
        """Start the loaded ramp/soak program."""
        ...

    def stop_program(self) -> None:
        """Stop the running program."""
        ...

    def read_run_status(self) -> RunMode:
        """Read the current run mode."""
        ...

    def read_segment(self) -> int:
        """Read current segment number."""
        ...

    def read_segment_elapsed(self) -> int:
        """Read elapsed time in current segment."""
        ...

    def read_alarm(self) -> bool:
        """Read alarm status (True if any alarm active)."""
        ...

    def start_autotune(self) -> None:
        """Trigger auto-tuning."""
        ...

    def stop_autotune(self) -> None:
        """Stop auto-tuning."""
        ...
