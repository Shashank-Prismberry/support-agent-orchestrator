"""Provider-independent specialist generation ports."""

from dataclasses import dataclass
from typing import Protocol

from support_agent_orchestrator.ports.routing import RoutingMessage


@dataclass(frozen=True)
class GenerationRequest:
    """Sanitized prompt input for an assistant response generator."""

    system_instruction: str
    messages: tuple[RoutingMessage, ...]


class AgentResponseGenerator(Protocol):
    """Provider-independent async port for generating assistant response text."""

    async def generate(self, request: GenerationRequest) -> object: ...
