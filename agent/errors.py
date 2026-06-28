"""Structured error types for the agentic loop (BRIEF §5 / §8).

Each error carries enough context for the repair prompt to produce a targeted fix:
the error type itself tells the LLM what class of problem it is (syntax vs geometry
vs inference), and the message + details give the specifics.

The goal: the repair LLM should be able to pattern-match against the error type
without having to parse an opaque string.
"""


class LudwigError(Exception):
    """Base for all Ludwig loop errors."""
    message: str

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InferenceError(LudwigError):
    """The inference provider failed/returned empty/timed out — no generated code."""
    provider: str

    def __init__(self, message: str, provider: str = "") -> None:
        self.provider = provider
        super().__init__(message)


class SyntaxError_(LudwigError):
    """The generated program has a Python syntax error."""
    line: int

    def __init__(self, message: str, line: int = 0) -> None:
        self.line = line
        super().__init__(message)


class GeometryBuildError(LudwigError):
    """OCCT geometry build failed (StdFail_NotDone, invalid solid, etc.)."""
    operation: str      # "fillet", "hole", "boolean", "unknown"

    def __init__(self, message: str, operation: str = "unknown") -> None:
        self.operation = operation
        super().__init__(message)


class MissingElementError(LudwigError):
    """The program did not assign a valid Element to the `element` variable."""
    def __init__(self, message: str = "") -> None:
        super().__init__(message or "program did not assign an Element to `element`")


class CriticError(LudwigError):
    """The critic itself raised an exception during evaluation."""
    critic_name: str

    def __init__(self, message: str, critic_name: str = "") -> None:
        self.critic_name = critic_name
        super().__init__(message)


__all__ = [
    "LudwigError", "InferenceError", "SyntaxError_", "GeometryBuildError",
    "MissingElementError", "CriticError",
]
