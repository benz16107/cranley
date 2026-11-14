"""Streamable HTTP at `/mcp` on the API, read-only (the HTTP door gets no workspace writes or agent turns)."""
from __future__ import annotations

import contextlib

from .server import build


def mount(app) -> None:
    """Add POST/GET /mcp to a FastAPI app and run the MCP session manager inside the app's lifespan."""
    server = build(write=False)
    server.settings.streamable_http_path = "/mcp"
    app.router.routes.extend(server.streamable_http_app().routes)  # one exact route, nothing shadowed
    before = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(a):
        async with server.session_manager.run(), before(a) as state:
            yield state
    app.router.lifespan_context = lifespan
