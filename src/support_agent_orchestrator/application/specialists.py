"""Injected specialist nodes for AGT-1.2."""

from collections.abc import Mapping
from typing import Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from support_agent_orchestrator.application.prompts import (
    AgentName,
    build_specialist_instruction,
)
from support_agent_orchestrator.domain.input import validate_internal_user_context
from support_agent_orchestrator.domain.state import AgentState, sanitize_messages
from support_agent_orchestrator.ports.agents import AgentResponseGenerator, GenerationRequest
from support_agent_orchestrator.ports.analysis import (
    MAX_CONTEXT_CHARACTERS,
    MAX_CONTEXT_MESSAGE_CHARACTERS,
    MAX_CONTEXT_MESSAGES,
    MAX_CURRENT_REQUEST_CHARACTERS,
)
from support_agent_orchestrator.ports.routing import RoutingMessage


class SpecialistExecutionError(RuntimeError):
    """Safe specialist failure without provider details."""


class SpecialistContextError(ValueError):
    """Raised when a specialist receives a mismatched or invalid state."""


MAX_SPECIALIST_CONTEXT_MESSAGES = MAX_CONTEXT_MESSAGES
MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS = MAX_CONTEXT_MESSAGE_CHARACTERS
MAX_SPECIALIST_CONTEXT_CHARACTERS = MAX_CONTEXT_CHARACTERS
MAX_SPECIALIST_CURRENT_REQUEST_CHARACTERS = MAX_CURRENT_REQUEST_CHARACTERS
SPECIALIST_CONTEXT_TRUNCATION_MARKER = "[Earlier message truncated] "


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
        messages = _bounded_specialist_context(state["messages"])
        request = GenerationRequest(
            system_instruction=build_specialist_instruction(self.agent_name, context),
            messages=messages,
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


def _bounded_specialist_context(messages: list[AnyMessage]) -> tuple[RoutingMessage, ...]:
    """Prepare one current request and bounded earlier human/assistant turns."""

    current_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        None,
    )
    if current_index is None:
        raise SpecialistContextError("Specialist state has no current user request")

    current_request = messages[current_index]
    prior_turns = tuple(
        message
        for message in messages[:current_index]
        if isinstance(message, (HumanMessage, AIMessage))
    )[-MAX_SPECIALIST_CONTEXT_MESSAGES:]
    sanitized = sanitize_messages([*prior_turns, current_request])
    sanitized_current = sanitized[-1]
    current_text = sanitized_current.content
    if not current_text.strip():
        raise SpecialistContextError("Specialist state has an empty current request")
    if len(current_text) > MAX_SPECIALIST_CURRENT_REQUEST_CHARACTERS:
        raise SpecialistContextError("Specialist current request exceeds the size limit")

    bounded_prior: list[RoutingMessage] = []
    remaining = MAX_SPECIALIST_CONTEXT_CHARACTERS
    for message in reversed(sanitized[:-1]):
        if len(bounded_prior) >= MAX_SPECIALIST_CONTEXT_MESSAGES or remaining <= 0:
            break
        content = message.content
        content_limit = min(MAX_SPECIALIST_CONTEXT_MESSAGE_CHARACTERS, remaining)
        if len(content) > content_limit:
            marker_length = len(SPECIALIST_CONTEXT_TRUNCATION_MARKER)
            if content_limit <= marker_length:
                continue
            content = (
                SPECIALIST_CONTEXT_TRUNCATION_MARKER + content[-(content_limit - marker_length) :]
            )
        else:
            content = content[-content_limit:]
        if not content.strip():
            continue
        bounded_prior.append(RoutingMessage(role=message.type, content=content))
        remaining -= len(content)

    bounded_prior.reverse()
    bounded_prior.append(RoutingMessage(role="human", content=current_text))
    return tuple(bounded_prior)


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
