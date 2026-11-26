from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.routers.auth import limiter, router as auth_router
from app.routers.org import router as org_router
from app.routers.experiments import router as experiments_router
from app.routers.files_datasets import router as files_datasets_router
from app.routers.processing import router as processing_router
from app.routers.results import router as results_router
from app.routers.annotations import router as annotations_router
from app.routers.metrics import router as metrics_router
from app.routers.stimuli import router as stimuli_router

app = FastAPI(title="Kani API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(org_router)
app.include_router(experiments_router)
app.include_router(files_datasets_router)
app.include_router(processing_router)
app.include_router(results_router)
app.include_router(annotations_router)
app.include_router(metrics_router)
app.include_router(stimuli_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
