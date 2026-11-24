"""Port for provider-independent Supervisor intent routing."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RoutingMessage:
    """Text-only, metadata-free message supplied to a routing provider."""

    role: str
    content: str


@dataclass(frozen=True)
class RoutingInput:
    """Canonical provider input that excludes raw LangChain message objects."""

    messages: tuple[RoutingMessage, ...]


class SupervisorRouter(Protocol):
    """Select an agent from sanitized text without authorization input."""

    def route(self, routing_input: RoutingInput) -> object: ...
