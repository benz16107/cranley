# Workspace contract (Contract 5): notes for the web app

Types: `workspace.ts` (generated) and `workspace.schema.json`. Regenerate both with
`cd server && uv run python -m threshold.agent.export`; a test fails when the schema is stale.

**Reading.** `GET /api/workspace/{id}` returns `{doc, learned, seq}` (`?log=true` adds the log). `doc` is a
`Workspace`. Render it and nothing else. `learned` is the "What I have learned" list; each item carries the
`undo` op to send.

**Agent turns.** `POST /api/agent/turn` with `{workspace?, text?, sids?, places?, profile?, budget?}` streams
server-sent events: `workspace` `{id}` first, then one `op` per `LogEntry` as it applies, then `done`
(`{status: "done", summary, budget}`, `{status: "questions", questions}` or `{status: "needs_scope"}`) or `error`.
`places` are things to look at without a scan: `{property_id}`, `{address}` or `{geo: [lon, lat]}`. With neither
scans nor places, a turn with text searches for buildings itself. `budget` (`{model_calls, tool_runs, parallel}`,
defaults 40, 40, 4) bounds the turn; `done.budget` gives the limits, what was used (`used.model_calls`,
`used.tool_runs`, `used.refused_tool_runs`) and `stopped_by` (null, `"model calls"` or `"tool runs"`). Apply each entry's `op` with the
same reducer semantics as `server/threshold/agent/workspace.py:apply`, or refetch the doc.
When the status is `questions`, show the open `doc.questions` as a form. A question may arrive with `answer` already
set and `answered: false`: the value comes from the person's own words ("a 90 cm wide piano"); show it pre-filled for
them to confirm. `doc.brief.limits` lists, in plain sentences, what the person needs that no tool does; show it. Send each answer as
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

**Live progress.** While a tool runs, each step it reports arrives as `run.progress` `{id, step}`; append `step` to
that run's `steps` (only while its status is `running`). `run.finish` carries the full list.

**Places.** A run on a place has `place` (`{property_id}`, `{address}` or `{geo}`) and `sid: null`; its result scope
is `{property_id, sids}`, `{address, geo}` or `{geo}`. `doc.brief.scope.places` lists the places in the workspace. An
overlay may have `sid: null`: pins with `{geo: [lon, lat]}` anchors, drawn on the map only. A whole-property run
(the agent fanning one tool out over a property's scans) has one check per scan (`scan.<sid>`, status = that scan's
verdict, `findings` = its finding ids) and its panel id is `panel:<tool>:p<property id>`.

**Agent panels.** `agent:ranked` is the ranked comparison (a `RankedTable` with rows in rank order, then one `Note`
per candidate). `custom:<slug>` panels are composed by the agent for a question no tool covers; the server has already
dropped any block part that names a missing run, metric, check, finding, overlay or scan.

**Corrections that spread.** `pref.set` with `label.<sid>.<room>` re-checks the same scan and up to six sibling scans
of the property. It appends `pref.set` entries (`by: "system"`, `cause` = the correction's seq, `because` = its key):
`label.<sid2>.<room2>` where a sibling has the same old label and size, and `doubt.<sid>.<room>` (value `{label,
because}`) for rooms that now look doubtful. Each appears in `learned` with a sentence naming the correction, and
runs on the affected scans get `stale: true`. Undo one alone with its `undo` op; forgetting the correction (`undo`
of its seq, or `pref.set` of its key to null) forgets everything that came from it.

**Preferences across workspaces.** Workspaces on one profile merge their preferences key by key: a key keeps its
latest edit, whichever workspace made it, and a removed key stays removed.

**Binding.** Blocks name runs, findings and overlays by id. They never copy numbers. `MetricRow.metrics`,
`MiniChart.metrics` and `RankedTable.columns[].metric` are ids in the run's `result.metrics`. Hide a finding
that has `superseded_by` set. Draw an overlay only while `visible` is true.
