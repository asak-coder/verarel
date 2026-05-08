from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.observability.logging import configure_json_logging
from app.observability.metrics import MonitoringMiddleware, build_metrics_router
from app.observability.tracing import TracingConfig, instrument_app, instrument_httpx, instrument_redis
from app.database import engine
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.compatibility import router as compatibility_router
from app.routers.date_architect import router as date_architect_router
from app.routers.interactions import router as interactions_router
from app.routers.matches import router as matches_router
from app.routers.profile import router as profile_router
from app.routers.security import router as security_router
from app.routers.trust import router as trust_router
from app.routers.webhooks import router as webhooks_router

configure_json_logging()
instrument_httpx()
instrument_redis()

app = FastAPI(title="Aken API", version="1.0.0")

@app.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "aken-api",
            "version": "1.0.0",
        }
    )
app.add_middleware(MonitoringMiddleware)
instrument_app(app, TracingConfig(service_name="aken-api", enable_otel=True))

app.include_router(build_metrics_router())
app.include_router(auth_router)
app.include_router(interactions_router)
app.include_router(matches_router)
app.include_router(compatibility_router)
app.include_router(date_architect_router)
app.include_router(profile_router)
app.include_router(security_router)
app.include_router(trust_router)
app.include_router(webhooks_router)
app.include_router(chat_router)
