# Threshold (working name): rules for every agent in this repo

HackPrinceton Fall 2026, CoStar + Amazon + Peri + LangChain tracks. One platform where an agent composes a
workspace of tools for anyone whose need involves a building. Read `docs/ARCHITECTURE.md` before any work.

## Hard rules

1. **No sponsor data in git.** CoStar's terms forbid it and this repo goes public. Scans, panoramas, floor
   plans, aerial or drone images, CoStar records, `models_index.csv`, and anything derived from them
   (screenshots that show them, cached JSON, counts per building) stay in the data folder, which is outside
   the repo: `$THRESHOLD_DATA_DIR`, default `~/Code/hackathons/hackprinceton26-data`. Tests that need
   real data read fixtures from there and skip when it is missing. Unit tests use small hand-made plans.
2. **No keys in git, logs or reports.** Keys live in `$THRESHOLD_DATA_DIR/.env`. Never print them.
3. **Stay in your lane.** `docs/ARCHITECTURE.md` gives each workstream its folders. Do not edit another
   workstream's folder or a contract. If a contract is wrong or missing something, say so in your report
   and code around it; the lead changes contracts.
4. **Be gentle with the APIs.** Everyone at the event shares them. Stay well under 10 requests a second,
   cache every response on disk under `$THRESHOLD_DATA_DIR/cache`, and never loop over all 14,944 scans
   without the lead's say-so.
5. **Numbers never pass through model text.** A measurement goes from the calculation to the result object.
   A model may choose, label and explain; it may not state a measured value from memory.
6. **Say what you did not check.** Reliability labels (`high`, `medium`, `low`) on every source are part of
   the product.
7. No copyleft (GPL, AGPL) dependencies. No Co-Authored-By or "Generated with" lines in commits.

## Working rules

- Commit small and often on your own branch. Finish with every change committed.
- Verify by running: tests for engines, a real browser screenshot for UI (Playwright MCP; save screenshots
  under `$THRESHOLD_DATA_DIR/shots/<workstream>/`, never in the repo).
- Python: 3.12 through `uv` (`cd server && uv sync && uv run pytest`). Type hints, small pure functions,
  `pytest`. Web: `pnpm`, Vite, React 19, TypeScript. Look up library APIs with Context7 before using them;
  several are newer than your training data (three 0.187, R3F 9, Spark 2.4, MapLibre 6, deck.gl 9.4).
- Research that grounds this build is in `~/Code/scratch/hackprinceton/research/` (`SYNTHESIS.md`
  first). It is outside the repo on purpose.
- Do not start subagents unless your task says so.

## Design rules (anything a user sees)

Ben wants this to look as good as possible and unlike a generic AI-built dashboard. Before UI work, load
the design skills (`interfaces:build-design`, `tastemaker:tastemaker`, `emil-design-eng`,
`make-interfaces-feel-better`) and read `~/.claude/rules/design-tells.md` and `~/.claude/rules/ui-libraries.md`.
The design tokens and component rules are in `web/src/design/` once the shell workstream lands them; use
them and add nothing ad hoc.

## Final report (your last message)

Branch and head SHA; what works, with the evidence (test output, screenshot paths); what does not work yet;
contract problems you found; what you did not check.
