"""The model behind the agent: Claude through an Anthropic-compatible endpoint, configured from the environment
(ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, THRESHOLD_MODEL; the data folder's .env fills what is unset).

`Model` is the seam tests fake: the composer only ever calls `structured`."""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..config import env

T = TypeVar("T", bound=BaseModel)


class Model(Protocol):
    def structured(self, system: str, user: str, schema: type[T]) -> T: ...


def chat(max_tokens: int = 2048):
    from langchain_anthropic import ChatAnthropic
    e = env()
    if not e.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set (environment or $THRESHOLD_DATA_DIR/.env)")
    return ChatAnthropic(model=e.get("THRESHOLD_MODEL", "claude-sonnet-5-5"), api_key=e["ANTHROPIC_API_KEY"],
                         base_url=e.get("ANTHROPIC_BASE_URL") or None, max_tokens=max_tokens, max_retries=2)


class Claude:
    def __init__(self, max_tokens: int = 1024):
        self.max_tokens = max_tokens

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        return chat(self.max_tokens).with_structured_output(schema).invoke([("system", system), ("human", user)])
