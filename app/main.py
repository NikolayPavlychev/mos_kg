from fastapi import FastAPI

from app.api.middleware import RequestLoggingMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="Moscow Knowledge Graph API",
        version="0.1.0",
        description="API for Neo4j graph queries and AI-assisted querying.",
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(api_router, prefix="/api")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
