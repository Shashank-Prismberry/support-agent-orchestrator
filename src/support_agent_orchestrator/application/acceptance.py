"""Application service for versioned, idempotent inbound request acceptance."""

import hashlib
import json
from collections.abc import Mapping

from langchain_core.messages import HumanMessage

from support_agent_orchestrator.domain.acceptance import (
    AcceptanceCandidate,
    AtomicAcceptanceRecord,
    CanonicalizationVersion,
    InboundRequest,
    RequestAcceptance,
)
from support_agent_orchestrator.domain.state import sanitize_messages
from support_agent_orchestrator.ports.acceptance import AtomicRequestAcceptor
from support_agent_orchestrator.ports.analysis import RequestAnalysisInput

CURRENT_CANONICALIZATION_VERSION = 1
SUPPORTED_CANONICALIZATION_VERSIONS = (1,)


class RequestAcceptanceConflictError(RuntimeError):
    """Raised when an idempotency key is reused for a different request."""


class ConversationBusyError(RuntimeError):
    """Raised when a conversation already has an active execution."""


class UnsupportedFingerprintVersionError(RuntimeError):
    """Raised when the original fingerprint cannot be safely reproduced."""


class InvalidAcceptanceOutcomeError(RuntimeError):
    """Raised when the persistence port returns an invalid or incomplete outcome."""


class RequestAcceptanceService:
    """Canonicalize request payloads and delegate atomic acceptance to a port."""

    def __init__(
        self,
        acceptor: AtomicRequestAcceptor,
        *,
        supported_versions: tuple[CanonicalizationVersion, ...] = (
            CURRENT_CANONICALIZATION_VERSION,
        ),
    ) -> None:
        if not supported_versions or len(set(supported_versions)) != len(supported_versions):
            raise ValueError("At least one unique canonicalization version is required")
        if any(
            version not in SUPPORTED_CANONICALIZATION_VERSIONS for version in supported_versions
        ):
            raise ValueError("A configured canonicalization version is not supported")
        self._acceptor = acceptor
        self._supported_versions = supported_versions

    async def accept(self, request: InboundRequest) -> RequestAcceptance:
        """Accept or resolve a duplicate without generating the caller request ID."""

        if not isinstance(request, InboundRequest):
            raise TypeError("Request acceptance requires a validated inbound request")

        sanitized_message = sanitize_messages([HumanMessage(content=request.message)])[0].content
        # Reuse the analyzer's existing validation so accepted session messages
        # follow the same non-empty and size limits as request analysis.
        validated_input = RequestAnalysisInput(current_request=sanitized_message)
        prepared_request = request.model_copy(update={"message": validated_input.current_request})
        fingerprints = {
            version: _fingerprint(prepared_request, version) for version in self._supported_versions
        }
        candidate = AcceptanceCandidate(
            request=prepared_request,
            fingerprints_by_version=fingerprints,
        )
        record = await self._acceptor.accept(candidate)
        return _interpret_record(record, fingerprints)


def _fingerprint(request: InboundRequest, version: int) -> str:
    """Return a deterministic digest over accepted semantic request fields."""

    if version != 1:
        raise UnsupportedFingerprintVersionError(
            "The stored request fingerprint version is not supported"
        )

    canonical_payload = {
        "canonicalization_version": version,
        "message": request.message,
    }
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _interpret_record(
    record: AtomicAcceptanceRecord,
    fingerprints: Mapping[int, str],
) -> RequestAcceptance:
    if not isinstance(record, AtomicAcceptanceRecord):
        raise InvalidAcceptanceOutcomeError("Persistence returned an invalid acceptance outcome")

    if record.outcome == "unsupported_fingerprint_version":
        raise UnsupportedFingerprintVersionError(
            "The stored request fingerprint version is not supported"
        )
    if record.outcome == "conflict":
        raise RequestAcceptanceConflictError(
            "The request identifier was already used with a different payload"
        )
    if record.outcome == "conversation_busy":
        raise ConversationBusyError("The conversation already has an active execution")
    if record.outcome not in {"accepted", "duplicate"}:
        raise InvalidAcceptanceOutcomeError("Persistence returned an unknown acceptance outcome")
    if record.execution_id is None or record.message_id is None:
        raise InvalidAcceptanceOutcomeError("Persistence returned an incomplete acceptance outcome")

    if record.outcome == "duplicate":
        stored_version = record.stored_fingerprint_version
        if stored_version is None or stored_version not in fingerprints:
            raise UnsupportedFingerprintVersionError(
                "The stored request fingerprint version is not supported"
            )

    return RequestAcceptance(
        execution_id=record.execution_id,
        message_id=record.message_id,
        duplicate=record.outcome == "duplicate",
    )
