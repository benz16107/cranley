---
title: "Amazon: Best Practical AI Innovation"
---

Judged creativity, usefulness, technical implementation and user experience, 25% each.

**Angle.** AI someone would use every day: a person with a real need about a building gets an answer they can act on,
without learning a tool. And it works on their own home, not only on a dataset.

| Criterion | What serves it |
|---|---|
| Creativity | An agent that builds the interface per need instead of a chat box; physics and geometry instead of text answers. |
| Usefulness | The wheelchair, flood, fire, garage, pet and furniture tools answer questions people ask on forums every day. The iPhone scan makes it work on any building. |
| Technical | About 600 server tests and 90 web tests; every tool run on a 15-place demo set with a matrix of results (see Proof); FastAPI, deepagents, two cloud databases, our own 3D renderer and splat training. |
| User experience | The App look: one thing first on every screen, the rest folded; plain-word reliability chips; every panel resizable; guided first run; both themes; phone companion with live sync. |

**Adaptive intelligence** (a named focus area): Cranley keeps a profile of the
person across investigations. It holds who they are, what they answered, the settings they changed, the tools they
removed and the kinds of check they marked useful or not relevant, each with where it came from and a way to change or
forget it. A new investigation starts from it: the composer asks only what it does not know, tool inputs taken from it
say so on the result, and checks of a kind the person waved off are kept back. In a three-visit replay of one
wheelchair user the questions asked went 1, 0, 0, and the checks kept back 0, 3, 9.

| Amazon focus area | What a judge sees | Where |
|---|---|---|
| Agentic behavior | The agent also decides what not to do from what it knows: skip a question, leave out a tool, keep back checks; each decision is one row under "Because of what Cranley knows about you" | Agent panel, top |
| Real-world impact | A chair width said once is used on every later home: doorways, step-free route and bathroom door, with "Using your doorway width: 0.7 m" on each result | Any result drawer |
| Adaptive intelligence | A profile across investigations, each line with its source, Change and Forget; "Not relevant" hides that kind now and later, "Useful" lists it first | "Cranley knows" (agent panel, Home, Settings); Checks tab |
| User-friendly design | No profile form: it fills from answers and clicks the person makes anyway; Home says in one line how much is known | Home, under the brief field |
| Creative innovation | The proof is in the product: "How Cranley has adapted to you" counts what each investigation asked, reused and kept back, from the person's own logs | "Cranley knows", first section |

What the replay shows and does not (run 2026-11-14 19:47, each counted
from op logs by `threshold.agent.profile.measure`): questions asked went 1, 0, 0 in all three evaluation runs. "Checks
that matter" uses a rule fixed before the run (a check matters unless it is a kind the person waved off or comes from a
tool they removed), so it shows that a taste expressed once is honoured on new buildings, not that Cranley guesses
relevance nobody told it. Time to the first result and the number of tool runs did not change in a way the replay can
support: both follow the model's latency and choices; only the removed tool never comes back. It is one persona on three
buildings, a replay rather than a user study. Limits: the profile holds only facts some tool input uses (about 80 keys;
no budget or risk tolerance), it does not read facts out of free text, and there is no sign-in (the profile id lives in
the browser).

**Demo path.** Phone: scan a room with the iPhone app (demo cafe in the simulator), name the business, pick
Accessibility, get the PDF in seconds. Desktop: the same workspace updates live. Then the wheelchair search above.
