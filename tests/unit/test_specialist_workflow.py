import pytest

from support_agent_orchestrator.application.specialists import build_specialist_nodes
from support_agent_orchestrator.application.supervisor import InvalidTrustedContextError
from support_agent_orchestrator.domain.input import create_internal_graph_input
from support_agent_orchestrator.graph.workflow import build_orchestration_graph
from support_agent_orchestrator.ports.agents import GenerationRequest
from support_agent_orchestrator.ports.routing import RoutingInput


class Router:
    def __init__(self, destination):
        self.destination = destination

    def route(self, request: RoutingInput):
        return self.destination


class Generator:
    def __init__(self, text):
        self.text = text

    async def generate(self, request: GenerationRequest):
        return self.text


def specialist_set():
    return build_specialist_nodes(
        triage=Generator("t"), knowledge=Generator("k"), billing=Generator("b")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "destination,text", [("triage", "t"), ("knowledge", "k"), ("billing", "b")]
)
async def test_graph_routes_one_specialist_to_end(
    trusted_context, user_message, destination, text
) -> None:
    graph = build_orchestration_graph(
        Router(destination),
        specialists=specialist_set(),
    )
    result = await graph.ainvoke(
        create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    )

    assert result["active_agent"] == destination
    assert result["messages"][-1].content == text
    assert len(result["messages"]) == 2


@pytest.mark.asyncio
async def test_async_graph_rejects_plain_input(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(
        Router("triage"),
        specialists=specialist_set(),
    )

    with pytest.raises(TypeError, match="internal graph input"):
        await graph.ainvoke({})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_async_graph_maps_invalid_context_to_safe_error(
    trusted_context, user_message
) -> None:
    graph = build_orchestration_graph(
        Router("triage"),
        specialists=specialist_set(),
    )
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    object.__setattr__(graph_input, "user_context", None)

    with pytest.raises(InvalidTrustedContextError, match="validated trusted"):
        await graph.ainvoke(graph_input)


def test_none_specialists_preserves_placeholder_graph(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(Router("triage"))
    assert (
        graph.invoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )["active_agent"]
        == "triage"
    )


@pytest.mark.parametrize("mapping", [{}, {"triage": object(), "knowledge": object()}])
def test_graph_rejects_empty_or_incomplete_specialist_mapping(mapping) -> None:
    with pytest.raises(ValueError, match="Specialist mapping"):
        build_orchestration_graph(Router("triage"), specialists=mapping)


def test_graph_rejects_non_callable_specialist_mapping_value() -> None:
    with pytest.raises(TypeError, match="callable"):
        build_orchestration_graph(
            Router("triage"),
            specialists={"triage": object(), "knowledge": object(), "billing": object()},
        )
