# Threshold (working name)

An agent that builds you a workspace of tools for whatever you need to know about a building: will the
water reach the outlets, can a wheelchair get from the curb to the bathroom, what should a fire crew know
before it arrives, does our team fit in this office. Built at HackPrinceton Fall 2026 on Matterport interior
scans, Vexcel aerial imagery and CoStar records.

- `docs/ARCHITECTURE.md`: how it fits together and the contracts between parts
- `server/`: Python engines, tools, agent and API
- `web/`: the explorer (map, 3D dollhouse, panoramas, splats) and the workspace

No sponsor data or keys are in this repository. Bring your own keys in a `.env` (see `.env.example`).
