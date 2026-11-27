"""Domain contracts for accepting an inbound request idempotently."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RequestId = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
ConversationId = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
CanonicalizationVersion = Annotated[int, Field(strict=True, gt=0)]
RequestFingerprint = Annotated[str, StringConstraints(strict=True, min_length=64, max_length=64)]
AcceptanceOutcome = Literal[
    "accepted",
    "duplicate",
    "conflict",
    "unsupported_fingerprint_version",
    "conversation_busy",
]


class _AcceptanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TrustedRequestScope(_AcceptanceModel):
    """Scope copied from the authenticated boundary, not request content.

    Constructing or validating this model does not establish authentication
    provenance; callers must supply it only after authenticating and resolving
    trusted context.
    """

    org_id: UUID
    user_id: UUID
    conversation_id: ConversationId


class InboundRequest(_AcceptanceModel):
    """Caller-identified request content paired with separately trusted scope."""

    scope: TrustedRequestScope
    request_id: RequestId
    message: str


class AcceptanceCandidate(_AcceptanceModel):
    """Prepared request fingerprints offered to an atomic persistence adapter."""

    request: InboundRequest
    fingerprints_by_version: dict[int, RequestFingerprint]


class AtomicAcceptanceRecord(_AcceptanceModel):
    """Adapter outcome, including the stored version used for duplicate comparison."""

    outcome: AcceptanceOutcome
    execution_id: UUID | None = None
    message_id: UUID | None = None
    stored_fingerprint_version: int | None = None


class RequestAcceptance(_AcceptanceModel):
    """Accepted or previously accepted execution and its inbound session turn."""

    execution_id: UUID
    message_id: UUID
    duplicate: bool
