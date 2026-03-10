from __future__ import annotations

from fastapi import FastAPI

from .router import router


app = FastAPI(title="Talmudpedia Artifact Worker")
app.include_router(router)
