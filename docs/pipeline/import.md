# Data import

Positions and light trajectories tracked by other tools can be imported from CSV files on the experiment's Data Import tab. Imported data replaces Steps 1 to 3 and is recorded so that later steps treat it exactly like computed data.

## Matching files to videos

Each CSV is matched to a video in the experiment by file name: the name without its extension, ignoring case, must equal the video's name without its extension. For example `Trial_04.csv` matches `trial_04.mp4`. Files with no matching video fail on their own without stopping the rest.

Several files can be imported at once. The overall import run succeeds if at least one file was imported, and its `runtime_info` lists the outcome of each file.

## Position CSVs

**Endpoint:** `POST /processing-runs/csv-import`

**Layout.** One row per frame, with two columns per subject: `x1, y1, x2, y2, …`. An optional header row is skipped if it contains no numbers. Empty cells, `NaN`, `NA` and spreadsheet errors such as `#N/A` count as missing.

**Coordinates are relative to the arena center.** Each value is an offset, and the arena center is added to get pixel positions. The center comes from the video's newest light-tracking run, so **the light must be tracked or imported first**.

**What is created:**

1. A detections JSON and a trajectory CSV, each in its own dataset.
2. A stand-in detection run and tracking run, under the tool names "Subject Detector" and "Positional Tracker" with the version label `csv-import-1.0.0`.
3. One track per subject column, numbered from 0, and a `Track` row for each.
4. A kinematics run for each imported trajectory, started automatically once the import is committed.

Row numbers become frame numbers, starting at 0. A subject with a missing value in a row is simply absent from that frame. Imported positions are all treated as detected, never predicted.

**Frame rate.** An optional frame rate fills the timestamps and sets the kinematics units. Without it, timestamps are empty and kinematics are measured per frame.

## Light CSVs

**Endpoint:** `POST /processing-runs/light-csv-import`

**Layout.** Columns `frame`, `x` and `y`, in pixels. A position of `-1, -1` means the light was off or not visible.

**Derived values:**

- **Circle.** The center is the middle of the positions' bounding box, and the radius is the mean of its half-width and half-height. This assumes the light goes all the way around at least once.
- **Angle.** Each position's angle around the center, from -π to π, and a continuous version that follows the light across full turns.
- **Speed.** The angular velocity at each frame, from the positions on either side. Its mean gives the run's angular velocity and rotation period.

**What is created:** a light-trajectory CSV in the same format as Step 1, in a `trajectory_positions` dataset, and a stand-in light-tracking run under the tool name "Manual Circular Trajectory" with the version label `csv-import-1.0.0`. The derived center and radius are stored in its settings, where later steps look for them.

**Frame rate.** Without an override, the trajectory covers the whole video at the video's frame rate. With an override, it covers frame 0 up to the last frame in the CSV, at that rate.

**Stimulus or not.** The collective-behavior analysis treats an imported light as a stimulus if its mean angular velocity is above 0.01 rad/s. It then works out the light's angle at frame 0 from its first visible position.

## Code

`app.jobs.csv_import_job` and `app.jobs.light_csv_import_job`. See the [jobs reference](../reference/jobs.md).
