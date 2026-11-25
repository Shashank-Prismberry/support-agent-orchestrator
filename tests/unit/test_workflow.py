import pytest

from support_agent_orchestrator.application.supervisor import (
    InvalidTrustedContextError,
    SupervisorRoutingError,
)
from support_agent_orchestrator.domain.input import (
    InternalGraphInput,
    create_internal_graph_input,
)
from support_agent_orchestrator.graph.workflow import (
    AsyncOnlyGraphError,
    _active_agent_route,
    build_orchestration_graph,
)
from support_agent_orchestrator.ports.routing import RoutingInput


class DeterministicRouter:
    def __init__(self, destination: object) -> None:
        self.destination = destination

    def route(self, routing_input: RoutingInput) -> object:
        return self.destination


@pytest.mark.parametrize("destination", ["triage", "knowledge", "billing"])
def test_graph_routes_to_terminal_boundary(trusted_context, user_message, destination) -> None:
    graph = build_orchestration_graph(DeterministicRouter(destination))
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    result = graph.invoke(graph_input)

    assert result["active_agent"] == destination
    assert result["approval_status"] == "not_required"
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == user_message.content
    assert result["messages"][0].id != user_message.id


def test_graph_routes_invalid_provider_output_to_triage(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(DeterministicRouter({"route": "billing"}))
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    assert graph.invoke(graph_input)["active_agent"] == "triage"


def test_graph_requires_internal_graph_input(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(DeterministicRouter("billing"))
    raw_state = {
        "messages": [user_message],
        "user_context": trusted_context,
        "active_agent": None,
        "approval_status": "not_required",
    }

    with pytest.raises(TypeError, match="internal graph input"):
        graph.invoke(raw_state)  # type: ignore[arg-type]


def test_internal_graph_input_cannot_be_directly_constructed(trusted_context, user_message) -> None:
    with pytest.raises(TypeError, match="created by create_internal_graph_input"):
        InternalGraphInput(trusted_context, (user_message,))  # type: ignore[call-arg]


def test_internal_graph_input_rejects_invalid_factory_token(trusted_context, user_message) -> None:
    with pytest.raises(TypeError, match="created by create_internal_graph_input"):
        InternalGraphInput._from_factory(
            object(), user_context=trusted_context, messages=(user_message,)
        )


def test_graph_revalidates_context_before_invocation(trusted_context, user_message) -> None:
    graph = build_orchestration_graph(DeterministicRouter("billing"))
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])
    object.__setattr__(graph_input, "user_context", None)

    with pytest.raises(InvalidTrustedContextError, match="validated trusted"):
        graph.invoke(graph_input)


def test_graph_preserves_safe_router_failure(trusted_context, user_message) -> None:
    class FailingRouter:
        def route(self, routing_input: RoutingInput) -> object:
            raise RuntimeError("secret provider detail")

    graph = build_orchestration_graph(FailingRouter())
    graph_input = create_internal_graph_input(user_context=trusted_context, messages=[user_message])

    with pytest.raises(SupervisorRoutingError, match="routing provider failed") as error:
        graph.invoke(graph_input)

    assert error.value.__cause__ is None
    assert "secret provider detail" not in str(error.value)


def test_specialist_graph_rejects_sync_invoke_before_execution(
    trusted_context, user_message
) -> None:
    router = DeterministicRouter("triage")

    class Generator:
        async def generate(self, request):
            raise AssertionError("generator must not be called")

    from support_agent_orchestrator.application.specialists import build_specialist_nodes

    graph = build_orchestration_graph(
        router,
        specialists=build_specialist_nodes(
            triage=Generator(), knowledge=Generator(), billing=Generator()
        ),
    )

    with pytest.raises(AsyncOnlyGraphError, match="use ainvoke"):
        graph.invoke(
            create_internal_graph_input(user_context=trusted_context, messages=[user_message])
        )

    assert router.destination == "triage"


def test_conditional_route_rejects_missing_active_agent(trusted_context, user_message) -> None:
    state = create_internal_graph_input(
        user_context=trusted_context, messages=[user_message]
    ).to_state()

    with pytest.raises(ValueError, match="did not select"):
        _active_agent_route(state)
