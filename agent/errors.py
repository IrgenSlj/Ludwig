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


__all__ = [
    "LudwigError", "SyntaxError_", "GeometryBuildError", "MissingElementError",
]
