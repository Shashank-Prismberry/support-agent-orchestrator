"""LangGraph state contracts and message sanitization for the workflow."""

import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from support_agent_orchestrator.domain.context import TrustedUserContext

ActiveAgent = Literal["triage", "knowledge", "billing"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]

_BEARER_TOKEN_PATTERN = re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]+)", re.IGNORECASE)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}\b")
_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|pwd|api[_-]?key|secret(?:[_-]?(?:key|token))?|"
    r"token|access[_-]?token|refresh[_-]?token|auth(?:orization)?[_-]?token|"
    r"client[_-]?secret|private[_-]?key|credentials?|jwt)\b"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_SENSITIVE_METADATA_KEYS = frozenset(
    {"authorization", "access_token", "api_key", "password", "secret", "token"}
)
_DOCUMENTATION_PLACEHOLDERS = frozenset(
    {"token", "access_token", "your_token", "example-token", "sample-token", "redacted"}
)


class SensitiveMessageContentError(ValueError):
    """Raised without credential content when a restricted message field is supplied."""


class UnsupportedMessageContentError(ValueError):
    """Raised without payload details for unsupported non-text message content."""


class AgentState(TypedDict):
    """The minimal durable state required by the central orchestration graph."""

    messages: Annotated[list[AnyMessage], add_messages]
    user_context: TrustedUserContext
    active_agent: ActiveAgent | None
    approval_status: ApprovalStatus


def create_initial_state(
    *, user_context: TrustedUserContext, messages: Sequence[AnyMessage]
) -> AgentState:
    """Create initial state from already-trusted context and sanitized messages."""

    return {
        "messages": sanitize_messages(messages),
        "user_context": user_context,
        "active_agent": None,
        "approval_status": "not_required",
    }


def sanitize_messages(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    """Remove metadata and redact credential-like content before state/router use."""

    return [_sanitize_message(message) for message in messages]


def router_text(message: BaseMessage) -> str:
    """Return the sanitized text that is safe to provide to a routing provider."""

    return _redact_credentials(_extract_text(message.content))


def _sanitize_message(message: AnyMessage) -> AnyMessage:
    _reject_sensitive_metadata(message)
    text = router_text(message)

    if isinstance(message, HumanMessage):
        return HumanMessage(content=text, id=str(uuid4()))
    if isinstance(message, AIMessage):
        return AIMessage(content=text, id=str(uuid4()))
    if isinstance(message, SystemMessage):
        return SystemMessage(content=text, id=str(uuid4()))
    if isinstance(message, ToolMessage):
        return ToolMessage(content=text, id=str(uuid4()), tool_call_id="")
    if isinstance(message, ChatMessage):
        return ChatMessage(content=text, id=str(uuid4()), role=message.role)
    raise UnsupportedMessageContentError("Unsupported message content cannot enter graph state")


def _reject_sensitive_metadata(message: BaseMessage) -> None:
    metadata_values = (
        message.additional_kwargs,
        message.response_metadata,
        getattr(message, "tool_calls", None),
        getattr(message, "invalid_tool_calls", None),
        getattr(message, "tool_call_chunks", None),
        getattr(message, "artifact", None),
    )
    if any(_contains_restricted_value(value) for value in metadata_values):
        raise SensitiveMessageContentError("Restricted credentials cannot enter graph state")


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        text_blocks: list[str] = []
        for block in content:
            if not isinstance(block, Mapping):
                raise UnsupportedMessageContentError(
                    "Unsupported message content cannot enter graph state"
                )
            if _contains_restricted_value(block):
                raise SensitiveMessageContentError(
                    "Restricted credentials cannot enter graph state"
                )
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text_blocks.append(block["text"])
        return "\n".join(text_blocks)
    raise UnsupportedMessageContentError("Unsupported message content cannot enter graph state")


def _contains_restricted_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(_JWT_PATTERN.search(value) or _contains_non_placeholder_bearer(value))
    if isinstance(value, (bytes, bytearray)):
        return _contains_restricted_value(value.decode("utf-8", errors="ignore"))
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_METADATA_KEYS and nested_value:
                return True
            if _contains_restricted_value(nested_value):
                return True
        return False
    if isinstance(value, Sequence):
        return any(_contains_restricted_value(item) for item in value)
    return False


def _contains_non_placeholder_bearer(value: str) -> bool:
    return any(
        match.group(1).lower() not in _DOCUMENTATION_PLACEHOLDERS
        for match in _BEARER_TOKEN_PATTERN.finditer(value)
    )


def _redact_credentials(value: str) -> str:
    """Redact JWTs, Bearer tokens, and explicit assignments to common secret fields.

    Assignment redaction covers password/passwd/pwd, token variants, API keys,
    secrets, credentials, JWTs, and client/private keys using ``=`` or ``:``.
    This is targeted text sanitization, not detection of every secret format.
    """
    redacted = _CREDENTIAL_ASSIGNMENT_PATTERN.sub(
        lambda match: (
            f"{match.group(0)[: match.start('separator') - match.start()]}"
            f"{match.group('separator')}[REDACTED_CREDENTIAL]"
        ),
        value,
    )
    redacted = _JWT_PATTERN.sub("[REDACTED_CREDENTIAL]", redacted)

    def replace_bearer(match: re.Match[str]) -> str:
        if match.group(1).lower() in _DOCUMENTATION_PLACEHOLDERS:
            return match.group(0)
        return "Bearer [REDACTED_CREDENTIAL]"

    return _BEARER_TOKEN_PATTERN.sub(replace_bearer, redacted)
