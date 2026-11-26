"""Application boundary for safely invoking the request analyzer port."""

from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from pydantic import ValidationError

from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.domain.state import sanitize_messages
from support_agent_orchestrator.ports.analysis import (
    MAX_CONTEXT_CHARACTERS,
    MAX_CONTEXT_MESSAGE_CHARACTERS,
    MAX_CONTEXT_MESSAGES,
    RequestAnalysisInput,
    RequestAnalyzer,
)
from support_agent_orchestrator.ports.routing import RoutingMessage


class RequestAnalyzerProviderError(RuntimeError):
    """Safe error raised when the injected analyzer fails."""


class InvalidRequestAnalysisOutputError(RuntimeError):
    """Safe error raised when the analyzer returns an invalid result."""


@dataclass(frozen=True)
class AnalyzedRequest:
    """Validated analysis paired with the exact sanitized input sent to its analyzer."""

    analysis: RequestAnalysis
    request: RequestAnalysisInput


class RequestAnalysisService:
    """Sanitize and bound request context before calling an analyzer port."""

    def __init__(self, analyzer: RequestAnalyzer) -> None:
        self._analyzer = analyzer

    async def analyze(
        self,
        current_request: str,
        conversation_context: Sequence[AnyMessage] = (),
    ) -> RequestAnalysis:
        """Analyze sanitized request text without supplying trusted context."""

        return (await self.analyze_with_input(current_request, conversation_context)).analysis

    async def analyze_with_input(
        self,
        current_request: str,
        conversation_context: Sequence[AnyMessage] = (),
    ) -> AnalyzedRequest:
        """Return validated analysis and the exact prepared input sent to the analyzer."""

        context_messages = _recent_messages(conversation_context)
        sanitized = sanitize_messages([HumanMessage(content=current_request), *context_messages])
        current = sanitized[0]
        analyzer_input = RequestAnalysisInput(
            current_request=current.content,
            conversation_context=_bounded_context(sanitized[1:]),
        )

        provider_failed = False
        result: object = None
        try:
            result = await self._analyzer.analyze(analyzer_input)
        except Exception:
            provider_failed = True
        if provider_failed:
            raise RequestAnalyzerProviderError("The request analyzer failed") from None

        try:
            payload = result.model_dump() if isinstance(result, RequestAnalysis) else result
            analysis = RequestAnalysis.model_validate(payload, strict=True)
        except (ValidationError, TypeError, ValueError, AttributeError):
            raise InvalidRequestAnalysisOutputError(
                "The request analyzer returned invalid output"
            ) from None
        return AnalyzedRequest(analysis=analysis, request=analyzer_input)


def _recent_messages(messages: Sequence[AnyMessage]) -> tuple[AnyMessage, ...]:
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence):
        raise TypeError("Conversation context must be a sequence of messages")
    conversation_turns = tuple(
        message for message in messages if isinstance(message, (HumanMessage, AIMessage))
    )
    return conversation_turns[-MAX_CONTEXT_MESSAGES:]


def _bounded_context(messages: Sequence[AnyMessage]) -> tuple[RoutingMessage, ...]:
    selected: list[RoutingMessage] = []
    remaining = MAX_CONTEXT_CHARACTERS

    for message in reversed(messages):
        if len(selected) >= MAX_CONTEXT_MESSAGES or remaining <= 0:
            break
        content = message.content
        content = content[-min(len(content), MAX_CONTEXT_MESSAGE_CHARACTERS, remaining) :]
        if not content.strip():
            continue
        selected.append(RoutingMessage(role=message.type, content=content))
        remaining -= len(content)

    selected.reverse()
    return tuple(selected)
