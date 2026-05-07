import logging
import os

from fastapi import FastAPI

from src.api.routes import admin as admin_routes
from src.api.routes import groups as groups_routes
from src.api.routes import users as users_routes
from src.handlers.admin_handler import AdminHandler
from src.handlers.group_handler import GroupHandler
from src.handlers.user_handler import UserHandler

logger = logging.getLogger(__name__)


def create_app(
    config: dict,
    user_handler: UserHandler,
    group_handler: GroupHandler,
    admin_handler: AdminHandler,
) -> FastAPI:
    """Build a FastAPI app that exposes the same operations available via the
    Telegram chat interface. Handlers are reused verbatim so behavior stays
    consistent across the two surfaces."""
    app = FastAPI(title="telegram-groupfactory internal API", version="1.0.0")

    app.state.config = config
    app.state.user_handler = user_handler
    app.state.group_handler = group_handler
    app.state.admin_handler = admin_handler

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok"}

    app.include_router(users_routes.router)
    app.include_router(groups_routes.router)
    app.include_router(admin_routes.router)

    return app


def build_uvicorn_config(app: FastAPI):
    """Return a uvicorn.Config bound to API_HOST / API_PORT env vars."""
    import uvicorn

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()

    logger.info("Internal REST API will listen on %s:%s", host, port)
    return uvicorn.Config(app, host=host, port=port, log_level=log_level, lifespan="on")
