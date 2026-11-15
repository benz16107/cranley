---
title: FAQ
description: Short answers about what Cranley can tell you and what it cannot.
---

## Is a result an inspection?

No. A result is a planning aid. Flood and fire results in particular are for planning. Each report ends with a list of what was not checked, and anything that matters should be measured on site.

## Where do the numbers come from?

From a calculation on the scan, the aerial data or the record. A number goes from the calculation to a result object to the screen. The language model picks tools, labels and explains. It is never the source of a measured value, and a grader rejects an agent message that states one. See [findings and reliability](/docs/concepts/findings-and-reliability/).

## What happens when a scan cannot answer?

The tool returns an `unknown` verdict with the reason, such as no wall graph, no door data or no location. Many scans have no wall graph, so every tool checks the plan's quality first.

## Does it work on my own home?

Yes, through the iPhone app. It scans a room with LiDAR, using Apple RoomPlan, and the server converts the export to the same plan format. A phone scan has walls, doors, windows, rooms and objects. It has no photos, no mesh and no location, so tools that read panoramas or aerial imagery say they cannot answer. The app builds and runs in the simulator. It has not been installed on a phone yet.

## Can I run it without sponsor keys?

Yes, on your own scans or the two made-up test scans. See [getting started](/docs/getting-started/).

## Is there a hosted version?

No. The live app is not public, because its API serves sponsor data. You run it yourself with your own access.

## Can another agent use the tools?

Yes. Every tool is an MCP tool and a command of the `threshold` CLI. The MCP server is read-only unless it is started with `--write`. See [MCP server and CLI](/docs/mcp/).

## Which cities does it cover?

The scans we were given are in Houston and Los Angeles. Some map layers cover one city only. A phone scan works anywhere.

## Does this site show sponsor data?

No. Its pictures show made-up test scans and our own drawings. The example on each tool page comes from a hand-made phone scan, run with no keys and the network switched off.

## What is the licence?

All rights reserved. CoStar's hackathon terms, section 4.2, assign the project's intellectual property to CoStar. See [data sources and licences](/docs/data-sources/).
