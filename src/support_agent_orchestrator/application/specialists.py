"""Injected specialist nodes for AGT-1.2."""

from collections.abc import Mapping
from typing import Literal

from langchain_core.messages import AIMessage

from support_agent_orchestrator.application.prompts import (
    AgentName,
    build_specialist_instruction,
)
from support_agent_orchestrator.domain.input import validate_internal_user_context
from support_agent_orchestrator.domain.state import AgentState, sanitize_messages
from support_agent_orchestrator.ports.agents import AgentResponseGenerator, GenerationRequest
from support_agent_orchestrator.ports.routing import RoutingMessage


class SpecialistExecutionError(RuntimeError):
    """Safe specialist failure without provider details."""


class SpecialistContextError(ValueError):
    """Raised when a specialist receives a mismatched or invalid state."""


class SpecialistNode:
    """Async specialist node that appends exactly one generated AI message."""

    def __init__(self, agent_name: AgentName, generator: AgentResponseGenerator) -> None:
        self.agent_name = agent_name
        self._generator = generator

    async def __call__(self, state: AgentState) -> dict[str, list[AIMessage]]:
        self._validate_state(state)
        try:
            context = validate_internal_user_context(state["user_context"])
        except ValueError:
            raise SpecialistContextError("Specialist state has invalid user context") from None
        messages = sanitize_messages(state["messages"])
        request = GenerationRequest(
            system_instruction=build_specialist_instruction(self.agent_name, context),
            messages=tuple(
                RoutingMessage(role=message.type, content=message.content) for message in messages
            ),
        )

        result: object | None = None
        provider_failed = False
        try:
            result = await self._generator.generate(request)
        except Exception:
            provider_failed = True
        if provider_failed:
            raise SpecialistExecutionError("The specialist generator failed")
        if not isinstance(result, str) or not result.strip():
            raise SpecialistExecutionError("The specialist generator returned invalid output")
        return {"messages": [AIMessage(content=result.strip())]}

    def _validate_state(self, state: Mapping[str, object]) -> None:
        if not isinstance(state, Mapping):
            raise SpecialistContextError("Specialist state is malformed")
        if "active_agent" not in state or "user_context" not in state or "messages" not in state:
            raise SpecialistContextError("Specialist state is missing required fields")
        if state["active_agent"] != self.agent_name:
            raise SpecialistContextError("The active agent does not match the specialist")
        if not isinstance(state["user_context"], Mapping) and not hasattr(
            state["user_context"], "model_dump"
        ):
            raise SpecialistContextError("Specialist state has invalid user context")
        messages = state["messages"]
        if isinstance(messages, (str, bytes)) or not isinstance(messages, list):
            raise SpecialistContextError("Specialist state has invalid messages")


def build_specialist_nodes(
    *,
    triage: AgentResponseGenerator,
    knowledge: AgentResponseGenerator,
    billing: AgentResponseGenerator,
) -> dict[Literal["triage", "knowledge", "billing"], SpecialistNode]:
    """Build the three independently injected specialist nodes."""

    return {
        "triage": SpecialistNode("triage", triage),
        "knowledge": SpecialistNode("knowledge", knowledge),
        "billing": SpecialistNode("billing", billing),
    }
