"""The model behind the agent: Claude through an Anthropic-compatible endpoint, configured from the environment
(ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, THRESHOLD_MODEL; the data folder's .env fills what is unset).

`Model` is the seam tests fake: the composer only ever calls `structured`."""
from __future__ import annotations

import os
from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..config import env

T = TypeVar("T", bound=BaseModel)


class Model(Protocol):
    def structured(self, system: str, user: str, schema: type[T]) -> T: ...


def tracing() -> bool:
    """LangSmith traces every agent turn (main agent, subagents, tool calls, approvals) when LANGSMITH_API_KEY is in
    the data folder's .env; LANGSMITH_TRACING=false turns it off (tests do). LangChain reads os.environ, so copy it."""
    e = env()
    on = bool(e.get("LANGSMITH_API_KEY")) and e.get("LANGSMITH_TRACING", "true").lower() != "false"
    if on:
        for k in ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"):
            if e.get(k):
                os.environ.setdefault(k, e[k])
        os.environ.setdefault("LANGSMITH_PROJECT", "threshold")
    os.environ["LANGSMITH_TRACING"] = "true" if on else "false"
    return on


def chat(max_tokens: int = 2048):
    from langchain_anthropic import ChatAnthropic
    tracing()
    e = env()
    if not e.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set (environment or $THRESHOLD_DATA_DIR/.env)")
    return ChatAnthropic(model=e.get("THRESHOLD_MODEL", "claude-sonnet-5-5"), api_key=e["ANTHROPIC_API_KEY"],
                         base_url=e.get("ANTHROPIC_BASE_URL") or None, max_tokens=max_tokens, max_retries=2)


class Claude:
    def __init__(self, max_tokens: int = 1024):
        self.max_tokens = max_tokens

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        # json_schema, not forced tool calling: the endpoint's model refuses forced tool use with thinking on
        return chat(self.max_tokens).with_structured_output(schema, method="json_schema").invoke(
            [("system", system), ("human", user)])
