"""Where the agent keeps its own state between requests, next to the workspaces:

- LangGraph checkpoints, so a turn that paused for the person's approval resumes later, in any server process and
  after a restart (collections `agent_checkpoints` and `agent_checkpoint_writes`, kept for a week).
- The LangGraph store behind the agents' `/memories/` folder: what earlier investigations learned about a building,
  per profile (collection `agent_memory`).

MongoDB when the workspaces live there (THRESHOLD_STORE=mongo), else in this process's memory."""
from __future__ import annotations

import functools

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

CHECKPOINT_TTL_S = 7 * 24 * 3600


@functools.cache
def _memory() -> tuple:
    return InMemorySaver(), InMemoryStore()


@functools.cache
def _mongo(store) -> tuple:
    from langgraph.checkpoint.mongodb import MongoDBSaver
    from langgraph.store.mongodb import MongoDBStore
    saver = MongoDBSaver(store.client, db_name=store.db.name, checkpoint_collection_name="agent_checkpoints",
                         writes_collection_name="agent_checkpoint_writes", ttl=CHECKPOINT_TTL_S)
    return saver, MongoDBStore(store.db["agent_memory"])  # no vector index: the M0 cluster's three are taken


def saver_and_store(workspace_store) -> tuple:
    """(checkpointer, store) for the workspace store a session uses."""
    if hasattr(workspace_store, "client") and hasattr(workspace_store, "db"):
        return _mongo(workspace_store)
    return _memory()
