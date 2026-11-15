---
title: Cranley docs
description: How to run Cranley, how it is built, and a reference for every tool, the HTTP API and the MCP server.
---

Cranley is one place where an agent assembles the tools a person's need requires and checks real buildings, inside and out. These docs cover how to run it, the ideas it is built on, and a reference for every part.

The code name `threshold` stays on the Python package, the command line and the MCP server. Where a command says `threshold`, that is Cranley.

## Start here

- [Getting started](/docs/getting-started/): run the server and the web app, with your own keys or with none.
- [FAQ](/docs/faq/): what it can and cannot tell you.

## Concepts

- [The workspace](/docs/concepts/workspace/): one document that the agent and the person both edit.
- [Tools](/docs/concepts/tools/): a manifest and a handler.
- [Personas](/docs/concepts/personas/): presets of tools and thresholds for a kind of user.
- [Findings and reliability](/docs/concepts/findings-and-reliability/): where every number comes from.
- [The agent](/docs/concepts/agent/): the composer and the investigator.

## Reference

- [Tool reference](/docs/tools/): one page per tool, generated from its manifest and from a real run on a made-up test scan.
- [MCP server and CLI](/docs/mcp/): every tool from Claude Code, Claude Desktop, Cursor or a terminal.
- [HTTP API](/docs/reference/api/): generated from the server's OpenAPI schema.
- [Result format](/docs/reference/result-format/), [personas](/docs/reference/personas/) and [map layers](/docs/reference/layers/).

## Project

- [Architecture](/docs/architecture/), [data sources and licences](/docs/data-sources/), [phone and iPhone app](/docs/phone/) and [sponsor integrations](/docs/sponsor-integrations/).

## How these docs stay true

The tool pages, the API pages, the personas, the map layers, the result format and the MCP page are written by `site/scripts/generate.py` from the code. When a tool or a route changes, running the generator again changes the page. The pages written by hand are this one, getting started, the concepts, architecture, data sources, the phone page and the FAQ.
