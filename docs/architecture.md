# Architecture

- **API layer** (`app/routers`). One router per area: authentication, laboratories and experiments, videos, files and datasets, processing runs, and one per pipeline step. Routers validate requests, check that the referenced records exist, create database rows, and start background jobs. Their endpoints are documented at `/docs`.
- **Jobs** (`app/jobs`). One module per pipeline step. A job opens its own database session, runs the computation, stores the output files and records what it did. See [Background jobs](jobs.md).
- **Computation** (`app/cv`, `app/tracking`, `app/analysis`, `app/pipelines`). Plain functions with no database access: arena and subject detection, tracking, kinematics, order parameters, clustering and Markov models. Jobs call them in a worker thread.
- **Data** (`app/models`, `app/database.py`, `app/crud`). SQLAlchemy models of the tables created by `schema.sql`, the async engine and session factory, and generic helpers for loading, listing, creating and deleting rows. See [Data model](data-model.md).
- **Storage** (`app/storage.py`). Writes files under the storage root and turns stored keys back into paths. See [Storage](storage.md).
- **Security** (`app/security.py`, `app/deps.py`). Password hashing, tokens, and the dependencies that identify the current user. See [Authentication](auth.md).
- **Configuration** (`app/config.py`). Settings read from `.env`.

## Module map

| Module | What it holds |
|---|---|
| `app/main.py` | The FastAPI app, CORS and rate-limit setup, router registration |
| `app/config.py` | Settings from `.env` |
| `app/database.py` | Engine, session factory, model base class |
| `app/storage.py` | Local file storage |
| `app/security.py` | Password hashing, access and refresh tokens |
| `app/deps.py` | Current-user and administrator dependencies |
| `app/progress.py` | In-memory progress for running jobs |
| `app/crud/base.py` | Generic database helpers, soft delete |
| `app/cv/plate_detection.py` | Arena detection |
| `app/cv/subject_detection.py` | Subject detection and the live preview |
| `app/cv/manual_tracking.py` | Light trajectory from a calibration |
| `app/cv/thumbnail.py` | Video thumbnails |
| `app/pipelines/video.py` | Video metadata, single frames, frame export |
| `app/tracking/positional_tracker.py` | The tracker |
| `app/tracking/kinematics.py` | Motion measures |
| `app/tracking/io.py` | Detection, trajectory and kinematics file formats |
| `app/analysis/order_parameters.py` | Windowed order parameters |
| `app/analysis/clustering.py` | Gaussian mixture state detection |
| `app/analysis/markov.py` | Transition matrix, stationary distribution, dwell times |
| `app/analysis/pipeline.py` | Offline multi-video analysis for scripts |
| `app/jobs/*` | One background job per step |
| `app/models/*` | Database models |
