from types import SimpleNamespace

import pytest

from agent.runtime import Agent, Config
from agent.skills import Skill
from agent.tests.conftest import write
from agent.tools import RunRecord, Toolbox
from agent.triage import triage

TARGET = "backend/app/features/todos/router.py"


def text(value):
    return SimpleNamespace(type="text", text=value)


def tool(name, **arguments):
    return SimpleNamespace(type="tool_use", id=f"id-{name}", name=name, input=arguments)


def response(stop_reason, *content):
    return SimpleNamespace(stop_reason=stop_reason, content=list(content),
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


class ScriptedClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot: the loop mutates it
        return self.responses.pop(0)


@pytest.fixture
def setup(repo):
    write(repo, TARGET, "x = 2\n")
    result = triage(repo, "main")
    toolbox = Toolbox(repo, result, {"s": Skill("s", "d", "b")}, RunRecord())
    return result, toolbox


def run(setup, *responses, max_turns=40):
    result, toolbox = setup
    client = ScriptedClient(*responses)
    return Agent(client, Config(max_turns=max_turns), "system", toolbox).run(result), client


def test_completes_when_every_target_is_decided(setup):
    outcome, client = run(
        setup,
        response("tool_use", tool("record_decision", path=TARGET, action="skip", reason="constant only")),
        response("end_turn", text("Skipped the router.")),
    )
    assert outcome.stop_reason == "completed"
    assert outcome.summary == "Skipped the router."
    assert outcome.usage.turns == 2 and outcome.usage.input_tokens == 20
    assert client.calls[0]["fallbacks"] == "default"


def test_nudges_then_reports_incomplete(setup):
    outcome, client = run(setup, *(response("end_turn", text("done?")) for _ in range(3)))
    assert outcome.stop_reason == "incomplete"
    nudge = client.calls[1]["messages"][-1]["content"]
    assert f"no decision recorded for {TARGET}" in nudge


def test_unrun_test_file_blocks_completion(setup):
    outcome, client = run(
        setup,
        response("tool_use",
                 tool("record_decision", path=TARGET, action="update", reason="new branch"),
                 tool("write_test_file", path="backend/tests/features/todos/test_router.py", content="x")),
        response("end_turn", text("done")),
        response("end_turn", text("done")),
        response("end_turn", text("done")),
    )
    assert outcome.stop_reason == "incomplete"
    assert "has not passed in its latest run" in client.calls[2]["messages"][-1]["content"]


def test_tool_errors_are_returned_to_the_model(setup):
    outcome, client = run(
        setup,
        response("tool_use", tool("write_test_file", path="backend/app/x.py", content="x")),
        response("refusal"),
    )
    assert outcome.stop_reason == "refusal"
    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "writes are limited" in result["content"]


def test_stops_at_max_turns(setup):
    outcome, _ = run(setup, *(response("tool_use", tool("list_files", path=".")) for _ in range(3)), max_turns=3)
    assert outcome.stop_reason == "max_turns"
    assert outcome.usage.turns == 3
