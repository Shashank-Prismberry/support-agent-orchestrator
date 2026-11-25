"""Validated domain contract for request analysis results."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RequestMode = Literal["quick", "context", "deep"]
RequestIntent = Literal["general_support", "knowledge", "billing", "mixed"]

_RequestedOutcome = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
]


class RequestAnalysis(BaseModel):
    """Classification description, independent of identity and execution policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: RequestMode
    intent: RequestIntent
    requested_outcomes: tuple[_RequestedOutcome, ...] = Field(min_length=1, max_length=10)
