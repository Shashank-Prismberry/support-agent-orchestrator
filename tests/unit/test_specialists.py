import pytest
from langchain_core.messages import HumanMessage

from support_agent_orchestrator.application.specialists import (
    SpecialistContextError,
    SpecialistExecutionError,
    SpecialistNode,
    build_specialist_nodes,
)
from support_agent_orchestrator.domain.input import create_internal_graph_input
from support_agent_orchestrator.ports.agents import GenerationRequest


class FakeGenerator:
    def __init__(self, result):
        self.result = result
        self.requests = []

    async def generate(self, request: GenerationRequest):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_name", ["triage", "knowledge", "billing"])
async def test_specialist_appends_one_response_and_uses_role_only(
    trusted_context, user_message, agent_name
) -> None:
    generator = FakeGenerator(" specialist response ")
    node = SpecialistNode(agent_name, generator)
    state = create_internal_graph_input(
        user_context=trusted_context,
        messages=[user_message],
    ).to_state()
    state["active_agent"] = agent_name

    update = await node(state)

    assert update["messages"][0].content == "specialist response"
    request = generator.requests[0]
    assert "Org_Admin" in request.system_instruction
    assert "refund.issue" not in request.system_instruction
    assert str(trusted_context.org_id) not in request.system_instruction
    assert request.messages[0].content == user_message.content


@pytest.mark.asyncio
async def test_specialist_rejects_active_agent_mismatch(trusted_context, user_message) -> None:
    node = SpecialistNode("billing", FakeGenerator("response"))
    state = create_internal_graph_input(
        user_context=trusted_context, messages=[user_message]
    ).to_state()
    state["active_agent"] = "triage"

    with pytest.raises(SpecialistContextError, match="does not match"):
        await node(state)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        {},
        {"active_agent": "triage"},
        {"active_agent": "triage", "user_context": None, "messages": []},
        {"active_agent": "triage", "user_context": "forged", "messages": []},
        {"active_agent": "triage", "user_context": {}, "messages": []},
        {"active_agent": "triage", "user_context": None, "messages": "not-a-list"},
        {"active_agent": "triage", "user_context": None, "messages": None},
    ],
)
async def test_specialist_rejects_malformed_state_without_raw_errors(state) -> None:
    node = SpecialistNode("triage", FakeGenerator("response"))

    with pytest.raises(SpecialistContextError, match="Specialist state"):
        await node(state)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_specialist_rejects_non_mapping_state() -> None:
    node = SpecialistNode("triage", FakeGenerator("response"))

    with pytest.raises(SpecialistContextError, match="state is malformed"):
        await node([])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_specialist_rejects_non_context_mapping_and_non_list_messages(
    trusted_context,
) -> None:
    node = SpecialistNode("triage", FakeGenerator("response"))
    state = {"active_agent": "triage", "user_context": 123, "messages": []}

    with pytest.raises(SpecialistContextError, match="invalid user context"):
        await node(state)  # type: ignore[arg-type]

    state["user_context"] = trusted_context
    state["messages"] = "bad"
    with pytest.raises(SpecialistContextError, match="invalid messages"):
        await node(state)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, 42, "", "   "])
async def test_specialist_rejects_invalid_generation_output(
    trusted_context, user_message, result
) -> None:
    node = SpecialistNode("triage", FakeGenerator(result))
    state = create_internal_graph_input(
        user_context=trusted_context, messages=[user_message]
    ).to_state()
    state["active_agent"] = "triage"

    with pytest.raises(SpecialistExecutionError, match="invalid output"):
        await node(state)


@pytest.mark.asyncio
async def test_specialist_sanitizes_provider_failure() -> None:
    class FailingGenerator:
        async def generate(self, request):
            raise RuntimeError("provider-secret")

    node = SpecialistNode("knowledge", FailingGenerator())
    context = {
        "id": "aaaaaaa1-1111-1111-1111-111111111111",
        "email": "alice@orga.com",
        "full_name": "Alice Admin",
        "org_id": "11111111-1111-1111-1111-111111111111",
        "customer_id": None,
        "role": "Org_Admin",
        "permissions": ["*"],
        "authorized_kb_tiers": ["public"],
    }
    from support_agent_orchestrator.domain.context import TrustedUserContext

    state = {
        "active_agent": "knowledge",
        "user_context": TrustedUserContext.model_validate(context),
        "messages": [HumanMessage(content="Current request")],
    }
    with pytest.raises(SpecialistExecutionError, match="generator failed") as error:
        await node(state)  # type: ignore[arg-type]
    assert "provider-secret" not in str(error.value)


def test_build_specialist_nodes_injects_three_independent_nodes() -> None:
    nodes = build_specialist_nodes(
        triage=FakeGenerator("t"), knowledge=FakeGenerator("k"), billing=FakeGenerator("b")
    )

    assert set(nodes) == {"triage", "knowledge", "billing"}
    assert len({id(node) for node in nodes.values()}) == 3
