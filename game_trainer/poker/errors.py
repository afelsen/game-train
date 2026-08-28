class PokerEngineError(Exception):
    """Base class for deterministic engine failures."""


class IllegalAction(PokerEngineError):
    """Raised when an action is not legal in the current state."""


class InvalidState(PokerEngineError):
    """Raised when a serialized or constructed state violates invariants."""

