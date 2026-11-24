import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from support_agent_orchestrator.domain.state import (
    SensitiveMessageContentError,
    UnsupportedMessageContentError,
    _extract_text,
    create_initial_state,
)


def test_initial_state_uses_approved_defaults_and_copies_messages(
    trusted_context, user_message
) -> None:
    messages = [user_message]
    state = create_initial_state(user_context=trusted_context, messages=messages)
    messages.append(HumanMessage(content="New message"))

    assert state["active_agent"] is None
    assert state["approval_status"] == "not_required"
    assert state["user_context"] is trusted_context
    assert len(state["messages"]) == 1
    assert state["messages"][0].content == user_message.content


def test_add_messages_appends_and_updates_by_message_id() -> None:
    original = HumanMessage(content="Original", id="message-1")
    added = AIMessage(content="Response", id="message-2")
    replacement = HumanMessage(content="Updated", id="message-1")

    combined = add_messages([original], [added])
    updated = add_messages(combined, [replacement])

    assert [message.id for message in updated] == ["message-1", "message-2"]
    assert updated[0].content == "Updated"


def test_initial_state_redacts_credentials_from_message_content(trusted_context) -> None:
    state = create_initial_state(
        user_context=trusted_context,
        messages=[HumanMessage(content="My header is Bearer sensitive-token")],
    )

    assert state["messages"][0].content == "My header is Bearer [REDACTED_CREDENTIAL]"


def test_initial_state_preserves_bearer_token_documentation_placeholders(trusted_context) -> None:
    content = "How do I configure Authorization: Bearer <token> in the API documentation?"
    state = create_initial_state(
        user_context=trusted_context,
        messages=[HumanMessage(content=content)],
    )

    assert state["messages"][0].content == content


@pytest.mark.parametrize(
    "message",
    [
        HumanMessage(content="safe", additional_kwargs={"authorization": "Bearer secret"}),
        AIMessage(content="safe", response_metadata={"access_token": "secret"}),
        ToolMessage(
            content="safe",
            tool_call_id="call-1",
            additional_kwargs={"payload": {"token": "secret"}},
        ),
    ],
)
def test_initial_state_rejects_credentials_in_metadata_or_tool_payloads(
    trusted_context, message
) -> None:
    with pytest.raises(SensitiveMessageContentError) as error:
        create_initial_state(user_context=trusted_context, messages=[message])

    assert "secret" not in str(error.value)


def test_initial_state_discards_safe_message_metadata(trusted_context) -> None:
    state = create_initial_state(
        user_context=trusted_context,
        messages=[HumanMessage(content="safe", additional_kwargs={"trace_id": "local-1"})],
    )

    assert state["messages"][0].additional_kwargs == {}


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content="assistant response", id="ai-1"),
        SystemMessage(content="system context", id="system-1"),
        ToolMessage(content="safe tool result", tool_call_id="call-1", id="tool-1"),
        ChatMessage(content="chat message", role="custom", id="chat-1"),
    ],
)
def test_initial_state_canonicalizes_supported_message_types(trusted_context, message) -> None:
    state = create_initial_state(user_context=trusted_context, messages=[message])

    assert state["messages"][0].type == message.type
    assert state["messages"][0].content == message.content


def test_initial_state_canonicalizes_safe_structured_text_content(trusted_context) -> None:
    state = create_initial_state(
        user_context=trusted_context,
        messages=[
            HumanMessage(
                content=[
                    {"type": "text", "text": "First paragraph"},
                    {"type": "text", "text": "Second paragraph"},
                ]
            )
        ],
    )

    assert state["messages"][0].content == "First paragraph\nSecond paragraph"


def test_initial_state_rejects_unsupported_or_sensitive_structured_content(trusted_context) -> None:
    with pytest.raises(SensitiveMessageContentError):
        create_initial_state(
            user_context=trusted_context,
            messages=[HumanMessage(content=[{"type": "tool_use", "token": "secret"}])],
        )

    with pytest.raises(UnsupportedMessageContentError):
        create_initial_state(
            user_context=trusted_context,
            messages=[HumanMessage(content=["not a content block"])],
        )


def test_initial_state_rejects_sensitive_bytes_and_sequence_metadata(trusted_context) -> None:
    with pytest.raises(SensitiveMessageContentError):
        create_initial_state(
            user_context=trusted_context,
            messages=[HumanMessage(content="safe", additional_kwargs={"trace": b"Bearer secret"})],
        )

    with pytest.raises(SensitiveMessageContentError):
        create_initial_state(
            user_context=trusted_context,
            messages=[
                HumanMessage(
                    content="safe",
                    response_metadata={"events": ["safe", "Bearer secret"]},
                )
            ],
        )


def test_initial_state_rejects_unsupported_message_type(trusted_context) -> None:
    unsupported = BaseMessage(content="safe", type="unsupported")

    with pytest.raises(UnsupportedMessageContentError):
        create_initial_state(user_context=trusted_context, messages=[unsupported])  # type: ignore[list-item]


def test_initial_state_preserves_named_bearer_token_placeholder(trusted_context) -> None:
    state = create_initial_state(
        user_context=trusted_context,
        messages=[HumanMessage(content="Use Bearer token in your example")],
    )

    assert state["messages"][0].content == "Use Bearer token in your example"


def test_initial_state_replaces_external_message_identifiers_and_tool_call_id(
    trusted_context,
) -> None:
    message = ToolMessage(
        content="safe",
        id="Bearer external-id",
        name="Bearer external-name",
        tool_call_id="Bearer external-call-id",
    )

    canonical = create_initial_state(user_context=trusted_context, messages=[message])["messages"][
        0
    ]

    assert canonical.id != message.id
    assert canonical.name is None
    assert canonical.tool_call_id == ""
    assert "Bearer" not in repr(canonical)


def test_non_text_message_content_is_rejected_without_payload_echo() -> None:
    with pytest.raises(UnsupportedMessageContentError) as error:
        _extract_text(123)

    assert "123" not in str(error.value)
