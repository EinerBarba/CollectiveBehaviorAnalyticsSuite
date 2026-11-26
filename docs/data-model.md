# Data model

The database is PostgreSQL, created from `schema.sql`. The SQLAlchemy models in `app/models` describe those tables but do not create them. This page explains how the tables fit together; the [models reference](reference/models.md) lists every column.

## Organization

```
Laboratory
└── Experiment
    ├── File (videos, results) ── FileVersion (the stored bytes)
    ├── Dataset ── DatasetVersion ── DatasetFile ──▶ FileVersion
    │                             └─ DatasetSpatialMetadata
    └── ProcessingRun ── ProcessingRunInput  ──▶ FileVersion or DatasetVersion
                      ├─ ProcessingRunOutput ──▶ DatasetVersion
                      ├─ Track
                      └─ MetricResult ──▶ MetricDefinition
```

Users create laboratories, laboratories hold experiments, and everything else belongs to an experiment.

## Files and versions

A **file** is a logical file, such as `trial_04.mp4` or a run's `positional_tracks.csv`. Its contents are held in **file versions**:

- Each version records its storage key (where the bytes are on disk), size, SHA-256 checksum, MIME type, uploader and upload time.
- Versions are added, never overwritten. Uploading a video with the same name to the same experiment adds a version to the existing file.
- `is_current` marks the version in use, and the file's `current_version_id` points at it.
- Confirming trajectories in the editor adds a new version of the tracking file and makes it current. Progress saves are also stored as versions of that file, but are never current and have their own MIME type, `application/vnd.kani.trajectory-progress+json`.
- `is_raw` marks original uploads, as opposed to derived results.

## Datasets

A **dataset** gives files a known meaning. It has a **type**, registered the first time a job uses it:

| Type | Produced by | Main file |
|---|---|---|
| `trajectory_positions` | Light tracking, subject tracking, imports | Trajectory CSV |
| `subject_detections` | Subject detection, position import | Detections JSON |
| `subject_kinematics` | Subject kinematics | Kinematics CSV |
| `collective_behavior_windows` | Collective behavior | Six analysis files |

Each dataset has one or more **dataset versions**. A version links to its files through **dataset file** rows, each with a role: `primary` for single-file outputs, and `windows`, `gmm_model`, `bic_scores`, `transition_matrix`, `markov_summary` and `dwell_runs` for collective-behavior outputs. `schema_version` names the file format, for example `positional-tracks-1.0`.

Positional datasets also have **spatial metadata**: the coordinate system (always `pixel`), units (`px`), sampling rate in Hz, and first and last frame.

Every job creates a new dataset with one version. Corrections to trajectories are new file versions, not new dataset versions, so a tracking dataset's version keeps pointing at the original automatic output.

## Processing runs and provenance

A **processing run** is one execution of a tool, and the center of the system's provenance:

- **Which tool.** Each run points at a **tool version**, which belongs to a **tool**. Both are registered on first use. Tool names, such as "Positional Tracker", are how later steps find runs.
- **Settings.** `parameters` holds everything the run was started with, including `source_file_version_id`, the video it was run for.
- **Results.** `runtime_info` holds summary values, such as track counts or the chosen number of states.
- **Status.** `queued`, then `running`, then `succeeded` or `failed`, with `error_message` on failure.
- **Inputs and outputs.** **Run inputs** name what the run read, with a role such as `raw_video`, `detections` or `trajectory`. **Run outputs** name the dataset versions it produced, usually with the role `primary_output`.

Following inputs and outputs from a video gives the full chain of everything derived from it. Deleting a video walks this chain; see [Storage](storage.md).

## Results attached to runs

- **Tracks.** One summary row per track in a trajectory dataset: its label and first and last frame. The positions themselves are in the CSV.
- **Metric definitions** give each metric a key, display name, unit and scope (`individual` or `group`).
- **Metric results** hold the values, each tied to its run and dataset version. Per-track kinematics results name their track in `value_json["track_label"]`.

## Accounts and access

- **Users** have an email, a password hash, and the flags `is_active` and `is_system_admin`.
- **Refresh tokens** are stored as hashes; see [Authentication](auth.md).
- **Roles** and **role assignments** let a user hold a role globally or for one laboratory or experiment. Assignments are only used to filter the list of runs a user can see; most endpoints do not check them.

## Soft deletion

Laboratories, experiments, subjects, files and datasets have a `deleted_at` column. Setting it hides the row from the generic helpers in `app.crud.base`, while keeping it in the database. Videos can also be deleted permanently by an administrator, which removes their derived data too.
