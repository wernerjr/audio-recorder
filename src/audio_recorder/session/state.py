from enum import Enum, auto


class SessionState(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()  # workers draining after stop
    DONE = auto()
    ERROR = auto()
