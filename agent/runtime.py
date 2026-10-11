"""The agent loop: a manual tool-use loop so the runtime, not the model, owns limits and completion."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent.tools import RunRecord, ToolError, Toolbox
from agent.triage import Triage

log = logging.getLogger("agent")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_COMPLETION_NUDGES = 2


@dataclass
class Config:
    model: str = "claude-sonnet-5-5"
    max_turns: int = 40
    max_tokens: int = 16_000
    effort: str = "medium"


@dataclass
class Usage:
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class RunResult:
    stop_reason: str  # "completed" | "incomplete" | "max_turns" | "refusal" | "max_tokens"
    summary: str
    usage: Usage = field(default_factory=Usage)


class MessagesClient(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


def missing_work(triage: Triage, record: RunRecord) -> list[str]:
    """What still stands between this run and its completion criterion."""
    gaps = [f"no decision recorded for {t.path}" for t in triage.targets if t.path not in record.decisions]
    for path in record.files_written:
        if record.last_result.get(path) is not True:
            gaps.append(f"{path} has not passed in its latest run")
    return gaps


def first_message(triage: Triage) -> str:
    return (
        "Triage for this run. Targets are the files you must decide on; ignored files are context only.\n\n"
        f"```json\n{json.dumps(triage.to_dict(), indent=2)}\n```"
    )


class Agent:
    def __init__(self, client: MessagesClient, config: Config, system: str, toolbox: Toolbox):
        self.client = client
        self.config = config
        self.system = system
        self.toolbox = toolbox

    def request(self, messages: list[dict]) -> Any:
        return self.client.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=self.system,
            tools=self.toolbox.specs,
            messages=messages,
            output_config={"effort": self.config.effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    def execute(self, block: Any) -> dict:
        try:
            content, is_error = self.toolbox.call(block.name, dict(block.input)), False
        except ToolError as exc:
            content, is_error = f"Error: {exc}", True
        except Exception as exc:  # a tool bug must not kill the run; the model can route around it
            log.exception("tool %s crashed", block.name)
            content, is_error = f"Error: internal tool failure ({type(exc).__name__})", True
        log.info("tool %s %s", block.name, "error" if is_error else "ok")
        return {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}

    def run(self, triage: Triage) -> RunResult:
        usage = Usage()
        messages: list[dict] = [{"role": "user", "content": first_message(triage)}]
        nudges = 0
        while usage.turns < self.config.max_turns:
            response = self.request(messages)
            usage.turns += 1
            usage.input_tokens += response.usage.input_tokens
            usage.output_tokens += response.usage.output_tokens
            usage.cache_read_input_tokens += getattr(response.usage, "cache_read_input_tokens", 0) or 0
            messages.append({"role": "assistant", "content": response.content})
            text = "".join(b.text for b in response.content if b.type == "text").strip()

            if response.stop_reason in ("refusal", "max_tokens"):
                return RunResult(response.stop_reason, text, usage)
            if response.stop_reason == "tool_use":
                results = [self.execute(b) for b in response.content if b.type == "tool_use"]
                messages.append({"role": "user", "content": results})
                continue

            gaps = missing_work(triage, self.toolbox.record)
            if not gaps:
                return RunResult("completed", text, usage)
            if nudges >= MAX_COMPLETION_NUDGES:
                return RunResult("incomplete", text, usage)
            nudges += 1
            messages.append({
                "role": "user",
                "content": "The run is not done yet:\n" + "\n".join(f"- {g}" for g in gaps),
            })
        return RunResult("max_turns", "", usage)
