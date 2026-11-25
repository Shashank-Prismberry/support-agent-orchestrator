"""Provider-independent specialist generation ports."""

from dataclasses import dataclass
from typing import Protocol

from support_agent_orchestrator.ports.routing import RoutingMessage


@dataclass(frozen=True)
class GenerationRequest:
    """Sanitized prompt input for a specialist generator."""

    system_instruction: str
    messages: tuple[RoutingMessage, ...]


class AgentResponseGenerator(Protocol):
    """Async generation capability injected into specialist nodes."""

    async def generate(self, request: GenerationRequest) -> object: ...
