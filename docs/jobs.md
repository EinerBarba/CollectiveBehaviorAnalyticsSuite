# Background jobs

Every pipeline step runs as a background job in `app/jobs`.

1. **Start.** The router has already created the processing run with status `queued`. The job opens its own database session, loads the run and sets it to `running` with a start time.
2. **Compute.** The job resolves its input files to paths on disk and runs the computation in a worker thread. Steps with progress call `set_progress` as they go, and `clear_progress` when done.
3. **Store files.** Each output is written with `storage.save_bytes` under `experiments/<experiment>/processing-runs/<run>/`, and registered as a new **file** with one **file version** holding its size and checksum.
4. **Record a dataset.** The job creates a **dataset** of the step's type, one **dataset version**, a **dataset file** link per output, and, for positional data, **spatial metadata** with the coordinate system, units, sampling rate and frame range.
5. **Record provenance.** It adds a **run input** for each file it read and a **run output** pointing at the dataset version. Some steps also store **tracks** or **metric results**.
6. **Finish.** The run becomes `succeeded`, with an end time and summary values in `runtime_info`, and everything is committed together.

If any step raises an error, the job rolls back what it had added, reloads the run, and marks it `failed` with the first 2,000 characters of the error in `error_message`.

| Step | Job | Tool name | Started by | Reads | Writes |
|---|---|---|---|---|---|
| Light tracking | `run_manual_tracking_job` | Manual Circular Trajectory | `POST /processing-runs/manual-tracking` | Video | Light trajectory CSV, `trajectory_positions` |
| Subject detection | `run_subject_detection_job` | Subject Detector | `POST /processing-runs/subject-detection` | Video | Detections JSON, `subject_detections` |
| Subject tracking | `run_positional_tracking_job` | Positional Tracker | `POST /processing-runs/positional-tracking` | Detections, video | Trajectory CSV, `trajectory_positions` |
| Subject kinematics | `run_subject_kinematics_job` | Subject Kinematics | `POST /processing-runs/subject-kinematics` | Trajectory CSV | Kinematics CSV, `subject_kinematics` |
| Collective behavior | `run_collective_behavior_experiment_job` | Collective Behavior Analysis | `POST /processing-runs/collective-behavior-experiment` | Light and tracking outputs of every video | Six files per condition, `collective_behavior_windows` |
| Position import | `run_csv_import_job` | Position CSV Import | `POST /processing-runs/csv-import` | Position CSVs | Detections and trajectories, then kinematics |
| Light import | `run_light_csv_import_job` | Light CSV Import | `POST /processing-runs/light-csv-import` | Light CSVs | Light trajectories |

## How steps find each other's results

Later steps locate earlier results through the run records rather than by file name:

- A run's settings include `source_file_version_id`, the video it was run for. The collective-behavior analysis and the CSV imports find the newest **succeeded** run of a given **tool name** for a video this way.
- A run's output is found by following its run output to the dataset version, then the dataset file with role `primary`, then the file version.
- The interface does the same through `GET /processing-run-outputs` and `GET /dataset-files`.

## Imports as stand-in runs

The CSV imports do not have a computation of their own to record. Instead they create already-finished runs under the same tool names the real steps use (for example "Positional Tracker"), with version labels such as `csv-import-1.0.0` and `csv_import: true` in their settings. Later steps then find imported data exactly as they would find computed data. See [Data import](pipeline/import.md).
