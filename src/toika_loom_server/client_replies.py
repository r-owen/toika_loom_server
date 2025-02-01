from __future__ import annotations

import dataclasses
import enum


class ConnectionStateEnum(enum.IntEnum):
    """Client websocket connection state."""

    DISCONNECTED = 0
    CONNECTED = 1
    CONNECTING = 2
    DISCONNECTING = 3


class MessageSeverityEnum(enum.IntEnum):
    """Severity for text messages"""

    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclasses.dataclass
class CommandProblem:
    """A problem with a command from the client"""

    type: str = dataclasses.field(init=False, default="CommandProblem")
    message: str
    severity: MessageSeverityEnum


@dataclasses.dataclass
class CurrentPickNumber:
    """The current pick and repeat numbers"""

    type: str = dataclasses.field(init=False, default="CurrentPickNumber")
    pick_number: int
    repeat_number: int


@dataclasses.dataclass
class JumpPickNumber:
    """Pending pick and repeat numbers"""

    type: str = dataclasses.field(init=False, default="JumpPickNumber")
    pick_number: int | None
    repeat_number: int | None


@dataclasses.dataclass
class LoomConnectionState:
    """The state of the server's connection to the loom"""

    type: str = dataclasses.field(init=False, default="LoomConnectionState")
    state: ConnectionStateEnum
    reason: str = ""


@dataclasses.dataclass
class LoomState:
    """The state output by the loom.

    In detail the states are (from the manual):

    * shed_fully_closed: True when the shed is fully closed.
    * pick_wanted: True when the loom is requesting the next pick.
    * error: True when the loom is not ready (trouble with the loom).
    """

    type: str = dataclasses.field(init=False, default="LoomState")
    shed_fully_closed: bool
    pick_wanted: bool
    error: bool

    @classmethod
    def from_state_word(cls, state_word: int) -> LoomState:
        """Construct a LoomState from the state value of the =s reply."""
        return cls(
            shed_fully_closed=bool(state_word & 0x01),
            pick_wanted=bool(state_word & 0x04),
            error=bool(state_word & 0x08),
        )


@dataclasses.dataclass
class PatternNames:
    """The list of loaded patterns (including the current pattern)"""

    type: str = dataclasses.field(init=False, default="PatternNames")
    names: list[str]


@dataclasses.dataclass
class WeaveDirection:
    """The weaving direction"""

    type: str = dataclasses.field(init=False, default="WeaveDirection")
    forward: bool
