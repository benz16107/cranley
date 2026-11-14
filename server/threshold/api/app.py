"""The API. Every module in this package that defines `router` is included, so workstreams add routes
by adding a file, never by editing this one."""
import importlib
import pathlib
import pkgutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Threshold")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for m in pkgutil.iter_modules([str(pathlib.Path(__file__).parent)]):
    if m.name != "app":
        mod = importlib.import_module(f"{__package__}.{m.name}")
        if hasattr(mod, "router"):
            app.include_router(mod.router)
