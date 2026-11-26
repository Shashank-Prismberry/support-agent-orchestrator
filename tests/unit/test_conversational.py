import asyncio

import pytest

from support_agent_orchestrator.application.conversational import (
    CONVERSATIONAL_INSTRUCTION,
    ConversationalResponseError,
    generate_conversational_response,
)
from support_agent_orchestrator.ports.agents import GenerationRequest


class Generator:
    def __init__(self, result: object) -> None:
        self.result = result
        self.request: GenerationRequest | None = None

    async def generate(self, request: GenerationRequest) -> object:
        self.request = request
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_conversational_response_uses_only_sanitized_current_request() -> None:
    generator = Generator(" Hello! ")

    response = await generate_conversational_response(generator, "Hi api_key=private-value")

    assert response.content == "Hello!"
    assert generator.request is not None
    assert generator.request.system_instruction == CONVERSATIONAL_INSTRUCTION
    assert len(generator.request.messages) == 1
    assert generator.request.messages[0].role == "human"
    assert "Hi" in generator.request.messages[0].content
    assert "private-value" not in generator.request.messages[0].content
    assert "REDACTED_CREDENTIAL" in generator.request.messages[0].content


@pytest.mark.asyncio
async def test_conversational_response_failure_is_safe() -> None:
    generator = Generator(RuntimeError("credential=private-value"))

    with pytest.raises(ConversationalResponseError) as error:
        await generate_conversational_response(generator, "Hello")

    assert str(error.value) == "The conversational response could not be generated"
    assert error.value.__cause__ is None
    assert "private-value" not in str(error.value)


@pytest.mark.asyncio
async def test_conversational_response_does_not_swallow_cancellation() -> None:
    generator = Generator(asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await generate_conversational_response(generator, "Hello")


@pytest.mark.asyncio
async def test_conversational_response_rejects_empty_output() -> None:
    with pytest.raises(ConversationalResponseError, match="response was invalid"):
        await generate_conversational_response(Generator("   "), "Hello")
