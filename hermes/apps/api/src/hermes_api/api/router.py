from fastapi import APIRouter

from hermes_api.api.routes import (
	agents,
	execution,
	health,
	observability,
	portfolio,
	resources,
	risk,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(execution.router, prefix="/execution", tags=["execution"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_router.include_router(resources.router, prefix="/resources", tags=["resources"])
api_router.include_router(observability.router, prefix="/observability", tags=["observability"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
