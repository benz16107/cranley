"""A per-turn budget: model calls (main agent and every subagent together), tool runs, and parallel work.

Two layers keep a turn inside it. Each agent has its own call limit (`ModelCallLimitMiddleware`, which ends that agent
politely), and a callback counts every chat model call in the turn and stops the turn when the total passes the cap.
Tool runs past the limit are refused with a sentence the model reads. Model calls made inside tools (a vision tool)
are not counted here.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from langchain_core.callbacks import BaseCallbackHandler


class BudgetSpent(RuntimeError):
    pass


@dataclass
class Budget:
    model_calls: int = 40   # hard cap for the whole turn
    tool_runs: int = 40
    parallel: int = 4       # scans run at once in a fan-out, and subagents at once
    main_calls: int = 14    # per-agent limits under the cap
    subagent_calls: int = 6
    property_calls: int = 8
    max_fan_out: int = 8    # scans one property fan-out may run
    calls: int = 0
    runs: int = 0
    refused_runs: int = 0
    stopped: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def take_run(self) -> bool:
        with self._lock:
            if self.runs >= self.tool_runs:
                self.refused_runs += 1
                self.stopped = self.stopped or "tool runs"
                return False
            self.runs += 1
            return True

    def count_call(self) -> None:
        with self._lock:
            self.calls += 1
            over = self.calls > self.model_calls
        if over:
            self.stopped = "model calls"
            raise BudgetSpent(f"turn budget of {self.model_calls} model calls spent")

    def callback(self) -> BaseCallbackHandler:
        budget = self

        class Counter(BaseCallbackHandler):
            raise_error = True  # the turn stops at the cap instead of carrying on

            def on_chat_model_start(self, serialized, messages, **kw):
                budget.count_call()

            def on_llm_start(self, serialized, prompts, **kw):
                budget.count_call()

        return Counter()

    def report(self) -> dict:
        d = vars(self)  # not asdict: it deep-copies the lock
        return {"limits": {k: d[k] for k in ("model_calls", "tool_runs", "parallel", "main_calls", "subagent_calls",
                                             "property_calls", "max_fan_out")},
                "used": {"model_calls": self.calls, "tool_runs": self.runs, "refused_tool_runs": self.refused_runs},
                "stopped_by": self.stopped}
