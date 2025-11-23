from fastapi import FastAPI

from .agent import AgentEndpoints
from .chat import ChatEndpoints
from .general import GeneralEndpoints
from .texts import TextEndpoints


def register_endpoints(app: FastAPI):
    """Attaches all endpoint routers to the FastAPI app."""
    app.include_router(GeneralEndpoints.router)
    app.include_router(ChatEndpoints.router)
    app.include_router(TextEndpoints.router)
    app.include_router(AgentEndpoints.router)

