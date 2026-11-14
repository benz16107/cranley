"""Composer evaluation: forty-one one-sentence briefs, each scored on the persona, the tools chosen, the questions asked
and, for a brief no preset fits, whether the composer says what it cannot do. "no_numbers" passes when every number in
the summary, reasons and limits is one the person said.

    uv run python -m threshold.agent.evaluate            # replay the recorded model answers (what the test runs)
    uv run python -m threshold.agent.evaluate --live     # ask the live model once per brief and record the answers
    uv run python -m threshold.agent.evaluate --missing  # ask it only for briefs with no recorded answer yet
    uv run python -m threshold.agent.evaluate --langsmith [--label x]  # the same run as a LangSmith experiment

Briefs and expectations: tests/agent/composer_briefs.json. Recorded answers: tests/agent/composer_recorded.json.
The table goes to $THRESHOLD_DATA_DIR/shots/agent/composer_eval[-<label>].md.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor

from ..config import DATA
from .composer import compose
from .workspace import BriefSet, QuestionAsk, ToolEnable, Workspace

TESTS = pathlib.Path(__file__).resolve().parents[2] / "tests" / "agent"
BRIEFS = TESTS / "composer_briefs.json"
RECORDED = TESTS / "composer_recorded.json"
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")  # any number the composer writes must be one the person said
CHECKS = ("persona", "tools", "questions", "cannot", "no_numbers")


def _text(user: str) -> str:
    return user.split("\n", 1)[0].removeprefix("Person said: ")


class Recorded:
    """Replays recorded answers by brief text."""
    def __init__(self, answers: dict[str, dict]):
        self.answers = answers

    def structured(self, system, user, schema):
        return schema.model_validate(self.answers[_text(user)])


class Recording:
    def __init__(self, model, answers: dict | None = None):
        self.model, self.answers = model, dict(answers or {})

    def structured(self, system, user, schema):
        if _text(user) in self.answers:
            return schema.model_validate(self.answers[_text(user)])
        out = self.model.structured(system, user, schema)
        self.answers[_text(user)] = out.model_dump(mode="json")
        return out


def score(b: dict, model) -> dict:
    ops = compose(b["brief"], Workspace(id="eval"), model)
    brief = next(o for o in ops if isinstance(o, BriefSet))
    tools = [o.tool for o in ops if isinstance(o, ToolEnable)]
    reasons = [o.reason for o in ops if isinstance(o, ToolEnable)]
    qs = [o.question for o in ops if isinstance(o, QuestionAsk)]
    stated = b.get("stated", {})
    checks = {
        "persona": (brief.persona or "none") in b["persona"],
        "tools": all(any(t in tools for t in group) for group in b.get("must", []))
                 and not set(tools) & set(b.get("never", [])),
        "questions": len(qs) <= 4 and set(b.get("asks", [])) <= {q.key for q in qs}
                     and all(q.answer == stated[q.key] for q in qs if q.key in stated),
        "cannot": bool(brief.limits) if b.get("cannot") else True,
        "no_numbers": not set(NUMBER.findall(" ".join([brief.summary or "", *reasons, *brief.limits])))
                      - set(NUMBER.findall(b["brief"])),
    }
    return {"id": b["id"], "brief": b["brief"], "persona": brief.persona or "none", "tools": tools,
            "questions": [{"key": q.key, "prefilled": q.answer} for q in qs], "cannot": brief.limits,
            "summary": brief.summary, "checks": checks, "ok": all(checks.values())}


def run(model, parallel: int = 4) -> list[dict]:
    briefs = json.loads(BRIEFS.read_text())
    with ThreadPoolExecutor(parallel) as ex:
        return list(ex.map(lambda b: score(b, model), briefs))


DATASET = "threshold-composer"


def langsmith_experiment(model, label: str = "") -> str:
    """Run the briefs as a LangSmith experiment on the dataset `threshold-composer` (created from the briefs file the
    first time), one feedback score per check, so prompt changes compare side by side. Returns the experiment name."""
    from langsmith import Client, evaluate

    from ..config import env
    from .llm import tracing
    tracing()
    client = Client(api_key=env()["LANGSMITH_API_KEY"])
    briefs = json.loads(BRIEFS.read_text())
    if not client.has_dataset(dataset_name=DATASET):
        ds = client.create_dataset(DATASET, description="One-sentence briefs for Threshold's composer, with the persona, "
                                                         "tools and questions each should produce.")
        client.create_examples(dataset_id=ds.id, examples=[{"inputs": {"brief": b}, "metadata": {"id": b["id"]}}
                                                           for b in briefs])
    checks = [(lambda k: lambda outputs: {"key": k, "score": int(outputs["checks"][k])})(k) for k in CHECKS]
    res = evaluate(lambda inputs: score(inputs["brief"], model), data=DATASET, evaluators=checks,
                   experiment_prefix=f"composer-{label or 'recorded'}", max_concurrency=4)
    return res.experiment_name


def table(rows: list[dict]) -> str:
    mark = lambda ok: "ok" if ok else "**FAIL**"  # noqa: E731
    lines = ["| id | persona | tools | questions | cannot | " + " | ".join(CHECKS) + " |", "|---" * (5 + len(CHECKS)) + "|"]
    for r in rows:
        q = ", ".join(x["key"] + (f" (prefilled {x['prefilled']})" if x["prefilled"] is not None else "")
                      for x in r["questions"]) or "none"
        lines.append(f"| {r['id']} | {r['persona']} | {', '.join(r['tools'])} | {q} | {'; '.join(r['cannot']) or '-'} | "
                     + " | ".join(mark(r["checks"][k]) for k in CHECKS) + " |")
    n = len(rows)
    lines += ["", f"{sum(r['ok'] for r in rows)} of {n} briefs pass every check. "
              + ", ".join(f"{k} {sum(r['checks'][k] for r in rows)}/{n}" for k in CHECKS) + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="ask the live model and record its answers")
    ap.add_argument("--label", default="", help="suffix for the saved table")
    ap.add_argument("--missing", action="store_true", help="ask the live model only for briefs not recorded yet")
    ap.add_argument("--langsmith", action="store_true", help="run it as a LangSmith experiment")
    a = ap.parse_args(argv)
    if a.langsmith:
        from .llm import Claude
        model = Claude() if a.live else Recorded(json.loads(RECORDED.read_text()))
        print("experiment", langsmith_experiment(model, a.label or ("live" if a.live else "")))
        return 0
    if a.live or a.missing:
        from .llm import Claude
        model = Recording(Claude(), json.loads(RECORDED.read_text()) if a.missing else None)
        rows = run(model)
        RECORDED.write_text(json.dumps(model.answers, indent=1, sort_keys=True) + "\n")
    else:
        rows = run(Recorded(json.loads(RECORDED.read_text())))
    out = DATA / "shots" / "agent" / f"composer_eval{'-' + a.label if a.label else ''}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = table(rows)
    out.write_text(f"# Composer evaluation{' (' + a.label + ')' if a.label else ''}\n\n" + text)
    out.with_suffix(".json").write_text(json.dumps(rows, indent=1))
    print(text)
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
