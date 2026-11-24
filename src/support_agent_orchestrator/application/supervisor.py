"""Supervisor node that performs intent routing only."""

from collections.abc import Mapping

from langchain_core.messages import AnyMessage

from support_agent_orchestrator.domain.input import validate_internal_user_context
from support_agent_orchestrator.domain.state import ActiveAgent, AgentState, sanitize_messages
from support_agent_orchestrator.ports.routing import RoutingInput, RoutingMessage, SupervisorRouter

_SUPPORTED_DESTINATIONS: frozenset[str] = frozenset({"triage", "knowledge", "billing"})
_DEFAULT_DESTINATION: ActiveAgent = "triage"


class InvalidTrustedContextError(ValueError):
    """Raised when graph state did not originate from the trusted boundary."""


class SupervisorRoutingError(RuntimeError):
    """Raised when the injected routing provider cannot produce a decision."""


class Supervisor:
    """Route a request to a specialist without executing specialist work."""

    def __init__(self, router: SupervisorRouter) -> None:
        self._router = router

    def __call__(self, state: AgentState) -> dict[str, ActiveAgent]:
        self._require_trusted_context(state)
        routing_input = _create_routing_input(sanitize_messages(state["messages"]))

        destination: object | None = None
        provider_failed = False
        try:
            destination = self._router.route(routing_input)
        except Exception:
            provider_failed = True

        if provider_failed:
            raise SupervisorRoutingError("The routing provider failed")

        return {"active_agent": self._normalize_destination(destination)}

    @staticmethod
    def _require_trusted_context(state: Mapping[str, object]) -> None:
        try:
            validate_internal_user_context(state.get("user_context"))
        except ValueError:
            raise InvalidTrustedContextError(
                "A validated trusted user context is required"
            ) from None

    @staticmethod
    def _normalize_destination(destination: object) -> ActiveAgent:
        if isinstance(destination, str) and destination in _SUPPORTED_DESTINATIONS:
            return destination  # type: ignore[return-value]
        return _DEFAULT_DESTINATION


def _create_routing_input(messages: list[AnyMessage]) -> RoutingInput:
    return RoutingInput(
        messages=tuple(
            RoutingMessage(role=message.type, content=message.content) for message in messages
        )
    )
