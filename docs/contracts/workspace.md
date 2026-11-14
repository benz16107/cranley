# Workspace contract (Contract 5): notes for the web app

Types: `workspace.ts` (generated) and `workspace.schema.json`. Regenerate both with
`cd server && uv run python -m threshold.agent.export`; a test fails when the schema is stale.

**Reading.** `GET /api/workspace/{id}` returns `{doc, learned, seq}` (`?log=true` adds the log). `doc` is a
`Workspace`. Render it and nothing else. `learned` is the "What I have learned" list; each item carries the
`undo` op to send.

**Agent turns.** `POST /api/agent/turn` with `{workspace?, text?, sids?, profile?}` streams server-sent events:
`workspace` `{id}` first, then one `op` per `LogEntry` as it applies, then `done` (`{status: "done", summary}`,
`{status: "questions", questions}` or `{status: "needs_scope"}`) or `error`. Apply each entry's `op` with the
same reducer semantics as `server/threshold/agent/workspace.py:apply`, or refetch the doc.
When the status is `questions`, show the open `doc.questions` as a form. Send each answer as
`question.answer`, then post the turn again without `text`.

**User ops.** `POST /api/workspace/{id}/ops` takes one op or a list; `by` is forced to `"user"`. Ops that teach
something append a `pref.set` (`by: "system"`, `cause` = the user op's seq). Ops that teach:
- `tool.disable`: the next composition leaves that tool out.
- `finding.add` with `feedback: {verdict: "rejected", reason}`: later runs leave the finding out.
- `pref.set` with an assumption id (an `x-pref` key such as `access.door_width_m`): later runs use the value,
  and earlier runs that used it get `stale: true`.
- `pref.set` with key `label.<sid>.<room>` and a room type: tools see the corrected label.
`POST /api/workspace/{id}/undo` with `{seq?}` undoes the user's latest op, or the entry `seq`, together with
what was learned from it. To rerun a tool after a control changes, send
`POST /api/tools/{id}/run?workspace={id}` with `{scan}`.

**Binding.** Blocks name runs, findings and overlays by id. They never copy numbers. `MetricRow.metrics`,
`MiniChart.metrics` and `RankedTable.columns[].metric` are ids in the run's `result.metrics`. Hide a finding
that has `superseded_by` set. Draw an overlay only while `visible` is true.
