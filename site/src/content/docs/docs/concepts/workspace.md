---
title: The workspace
description: One document per session, changed only through typed operations by the agent and the person alike.
---

A workspace is one JSON document for one session of work. It holds the brief, the enabled tools, the runs and their results, the findings, what is drawn on the building, the panels, the agent's plan, the person's preferences and a shortlist.

## One set of operations

The agent and the person change the document through the same operations. Each one is appended to a log with who did it, when, and which run it belongs to.

| Operation | What it does |
|---|---|
| `brief.set` | Sets what the person needs and which buildings are in scope |
| `question.ask`, `question.answer` | Asks for an input nothing else fills, and records the answer |
| `tool.enable`, `tool.disable` | Adds a tool to the workspace or takes it out |
| `run.start`, `run.progress`, `run.finish` | A tool run, its steps as they happen, and its result |
| `finding.add` | Adds or replaces a finding, and carries the person's feedback on it |
| `overlay.upsert`, `layer.upsert` | What is drawn on the building or the map |
| `panel.upsert` | A result panel, built from a fixed set of blocks |
| `camera.focus` | Points the view at what matters |
| `plan.set` | The agent's plan, shown as its progress |
| `pref.set` | A preference, such as the width of door the person needs |
| `shortlist.add`, `shortlist.remove` | The buildings worth a second look |

Undo is a log entry too. `POST /api/workspace/{id}/undo` undoes the person's latest operation together with what the agent learned from it.

## Operations that teach

Some of the person's operations change what happens next:

- Turning a tool off leaves it out of the next composition.
- Rejecting a finding keeps later runs from showing it.
- Editing an assumption, such as the door width, makes later runs use the new value and marks earlier runs that used the old one as stale.
- Correcting a room's label re-checks the same scan and up to six sibling scans of the property.

Each thing learned appears in a "What I have learned" list with its own undo.

## Panels

A panel is built only from twelve blocks: `VerdictHeader`, `MetricRow`, `CheckList`, `EvidenceStrip`, `RankedTable`, `MiniChart`, `FloorPlanMini`, `Controls`, `AssumptionChips`, `StepLog`, `Note` and `ActionBar`. Blocks name runs, findings and overlays by id. They never copy a number, so a panel cannot show a value that the result does not hold.

## Where it lives

By default a workspace is a file in the data folder. With `THRESHOLD_STORE=mongo` it lives in MongoDB Atlas, where a unique index on the workspace and the sequence number stops two writers from appending the same entry, and change streams carry each entry to every open browser and phone.

The schema and the TypeScript types are in `docs/contracts/` in the repository. The routes are under [agent and workspace](/docs/reference/api/agent/) in the API reference.
