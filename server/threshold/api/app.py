"""The API. Every module in this package that defines `router` is included, so workstreams add routes
by adding a file, never by editing this one."""
import importlib
import pathlib
import pkgutil
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

BINARY = re.compile(r"/(pano|floorplan|drone|splat|interior-splat|mesh)(/|$)")  # images and the splat: already compressed, and Range needs raw bytes


class JsonGZip(GZipMiddleware):
    """gzip for JSON answers (/api/buildings is a few MB uncompressed), not for images or the splat stream."""
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and BINARY.search(scope["path"]):
            return await self.app(scope, receive, send)
        return await super().__call__(scope, receive, send)


app = FastAPI(title="Threshold")
app.add_middleware(JsonGZip, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for m in pkgutil.iter_modules([str(pathlib.Path(__file__).parent)]):
    if m.name != "app":
        mod = importlib.import_module(f"{__package__}.{m.name}")
        if hasattr(mod, "router"):
            app.include_router(mod.router)
