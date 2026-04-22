from fastapi import FastAPI

from hermes_api.api.router import api_router
from hermes_api.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "environment": settings.app_env,
            "status": "bootstrapped",
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
