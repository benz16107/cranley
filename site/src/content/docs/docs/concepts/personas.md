---
title: Personas
description: A persona is a preset for a kind of user, with the tools that fit and the thresholds that fill their inputs.
---

A persona is a starting point for a kind of user: a wheelchair user, a fire captain, a Houston homeowner before a storm, a truck dispatcher, an office tenant.

Each one holds three things:

- **Who.** One sentence describing the person and their need.
- **Tools.** The tools that serve that need.
- **Thresholds.** Values that fill tool inputs, such as a door width of 0.815 m and a turning circle of 1.525 m for a wheelchair user looking for a home.

## How the composer uses them

The composer reads the person's sentence and chooses the persona whose "who" describes them. It starts from that preset's tools, drops the ones that do not fit what the person said and adds ones that do. When no preset fits, it chooses none and assembles the tools from the whole list.

A persona never limits what the person can do. Every tool can be turned on by hand, and every threshold can be edited. An edit is saved as a preference and used by later runs.

The full list, with each persona's tools and presets, is in the [persona reference](/docs/reference/personas/). It is generated from `server/threshold/agent/personas/`.
