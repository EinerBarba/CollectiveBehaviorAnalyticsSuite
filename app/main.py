"""Application entry point.

Creates the FastAPI app, attaches the rate limiter and CORS settings, and
registers every router. Start it with `uvicorn app.main:app`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.routers.auth import limiter, router as auth_router
from app.routers.videos import router as videos_router
from app.routers.org import router as org_router
from app.routers.experiments import router as experiments_router
from app.routers.files_datasets import router as files_datasets_router
from app.routers.processing import router as processing_router
from app.routers.results import router as results_router
from app.routers.annotations import router as annotations_router
from app.routers.metrics import router as metrics_router
from app.routers.stimuli import router as stimuli_router
from app.routers.manual_tracking import router as manual_tracking_router
from app.routers.positional_tracking import router as positional_tracking_router
from app.routers.subject_kinematics import router as subject_kinematics_router
from app.routers.subject_detection import router as subject_detection_router
from app.routers.collective_behavior import router as collective_behavior_router
from app.routers.cb_results import router as cb_results_router
from app.routers.trajectory_edit import router as trajectory_edit_router
from app.routers.csv_import import router as csv_import_router
from app.routers.light_csv_import import router as light_csv_import_router


app = FastAPI(title="Collective Behavior Analytics")
"""The ASGI application. Interactive API documentation is served at `/docs`."""

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
app.include_router(videos_router)
app.include_router(org_router)
app.include_router(experiments_router)
app.include_router(files_datasets_router)
app.include_router(processing_router)
app.include_router(results_router)
app.include_router(annotations_router)
app.include_router(metrics_router)
app.include_router(stimuli_router)
app.include_router(manual_tracking_router)
app.include_router(positional_tracking_router)
app.include_router(subject_kinematics_router)
app.include_router(subject_detection_router)
app.include_router(collective_behavior_router)
app.include_router(cb_results_router)
app.include_router(trajectory_edit_router)
app.include_router(csv_import_router)
app.include_router(light_csv_import_router)


@app.get("/health")
async def health():
    """Report that the server is running. Does not check the database."""
    return {"status": "ok"}
