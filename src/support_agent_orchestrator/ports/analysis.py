"""Provider-independent request analysis port and sanitized input contract."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from support_agent_orchestrator.domain.request_analysis import RequestAnalysis
from support_agent_orchestrator.ports.routing import RoutingMessage

MAX_CURRENT_REQUEST_CHARACTERS = 4_000
MAX_CONTEXT_MESSAGES = 10
MAX_CONTEXT_MESSAGE_CHARACTERS = 2_000
MAX_CONTEXT_CHARACTERS = 10_000
MAX_ROUTING_ROLE_CHARACTERS = 32


@dataclass(frozen=True)
class RequestAnalysisInput:
    """Sanitized current request and bounded relevant conversation context.

    Callers must sanitize message text before constructing this input. This
    contract contains no trusted identity, authorization, credential, approval,
    or capability data.
    """

    current_request: str
    conversation_context: tuple[RoutingMessage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.current_request, str) or not self.current_request.strip():
            raise ValueError("Current request must be non-empty text")
        if len(self.current_request) > MAX_CURRENT_REQUEST_CHARACTERS:
            raise ValueError("Current request exceeds the size limit")

        if not isinstance(self.conversation_context, tuple):
            raise TypeError("Conversation context must be a tuple of routing messages")
        if len(self.conversation_context) > MAX_CONTEXT_MESSAGES:
            raise ValueError("Conversation context exceeds the message limit")

        context_characters = 0
        for message in self.conversation_context:
            if not isinstance(message, RoutingMessage):
                raise TypeError("Conversation context must contain routing messages")
            if not isinstance(message.role, str) or not message.role.strip():
                raise ValueError("Conversation context roles must be non-empty text")
            if len(message.role) > MAX_ROUTING_ROLE_CHARACTERS:
                raise ValueError("A conversation context role exceeds the size limit")
            if not isinstance(message.content, str) or not message.content.strip():
                raise ValueError("Conversation context messages must be non-empty text")
            if len(message.content) > MAX_CONTEXT_MESSAGE_CHARACTERS:
                raise ValueError("A conversation context message exceeds the size limit")
            context_characters += len(message.content)

        if context_characters > MAX_CONTEXT_CHARACTERS:
            raise ValueError("Conversation context exceeds the total size limit")


@runtime_checkable
class RequestAnalyzer(Protocol):
    """Analyze sanitized request text without provider-specific dependencies."""

    async def analyze(self, request: RequestAnalysisInput) -> RequestAnalysis: ...
