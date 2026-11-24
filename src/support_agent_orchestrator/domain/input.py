"""Internal graph-input construction for authenticated application boundaries.

This module validates internal contracts only. A future API/worker boundary must
authenticate the Backend-issued token and resolve ``/auth/me`` before it calls
``create_internal_graph_input``. Validation cannot itself prove authentication
provenance.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import AnyMessage
from pydantic import ValidationError

from support_agent_orchestrator.domain.context import TrustedUserContext
from support_agent_orchestrator.domain.state import AgentState, sanitize_messages


class InvalidInternalGraphInputError(ValueError):
    """Raised when an internal caller supplies malformed graph input."""


_CONSTRUCTION_TOKEN = object()


@dataclass(frozen=True, init=False)
class InternalGraphInput:
    """Canonical input accepted by the internal orchestration graph wrapper."""

    user_context: TrustedUserContext
    messages: tuple[AnyMessage, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("InternalGraphInput must be created by create_internal_graph_input")

    @classmethod
    def _from_factory(
        cls,
        token: object,
        *,
        user_context: TrustedUserContext,
        messages: tuple[AnyMessage, ...],
    ) -> "InternalGraphInput":
        if token is not _CONSTRUCTION_TOKEN:
            raise TypeError("InternalGraphInput must be created by create_internal_graph_input")
        instance = object.__new__(cls)
        object.__setattr__(instance, "user_context", user_context)
        object.__setattr__(instance, "messages", messages)
        return instance

    def to_state(self) -> AgentState:
        """Revalidate and sanitize before every graph invocation."""

        return {
            "messages": sanitize_messages(self.messages),
            "user_context": validate_internal_user_context(self.user_context),
            "active_agent": None,
            "approval_status": "not_required",
        }


def create_internal_graph_input(
    *, user_context: TrustedUserContext, messages: Sequence[AnyMessage]
) -> InternalGraphInput:
    """Build sanitized graph input for use after authenticated context resolution."""

    return InternalGraphInput._from_factory(
        _CONSTRUCTION_TOKEN,
        user_context=validate_internal_user_context(user_context),
        messages=tuple(sanitize_messages(messages)),
    )


def validate_internal_user_context(value: object) -> TrustedUserContext:
    """Revalidate a context instance without claiming it proves authentication."""

    if not isinstance(value, TrustedUserContext):
        raise InvalidInternalGraphInputError("A validated trusted user context is required")

    try:
        return TrustedUserContext.model_validate(dict(value.__dict__))
    except ValidationError:
        raise InvalidInternalGraphInputError(
            "A validated trusted user context is required"
        ) from None
