"""Typed exceptions for doxygen-guard.

@brief Library-level errors that callers can catch; exit codes belong to the CLI.
@version 1.0
"""

from __future__ import annotations


## @brief Base class for all doxygen-guard errors raised to library callers.
#  @version 1.0
#  @req REQ-DDB-GUARD-014
class GuardError(Exception):
    """Base error carrying a summary message plus zero or more specific problems."""

    ## @brief Build an error carrying one or more human-readable problem descriptions.
    #  @version 1.0
    #  @req REQ-DDB-GUARD-014
    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.problems: list[str] = problems or []

    ## @brief Render the message followed by each individual problem.
    #  @version 1.0
    #  @req REQ-DDB-GUARD-014
    #  @return Multi-line description of the error and its problems
    def details(self) -> str:
        return "\n".join([self.message, *self.problems])

    ## @brief Render the full detail, so a caller printing str(e) sees every problem.
    #  @version 1.0
    #  @req REQ-DDB-GUARD-014
    #  @return Same text as details()
    def __str__(self) -> str:
        return self.details()


## @brief Raised when .doxygen-guard.yaml is unreadable or violates the config schema.
#  @version 1.0
#  @req REQ-DDB-GUARD-014
class ConfigError(GuardError):
    pass


## @brief Raised when the requirements catalog is missing, unreadable, or malformed.
#  @version 1.0
#  @req REQ-DDB-GUARD-011
class RequirementsError(GuardError):
    pass
