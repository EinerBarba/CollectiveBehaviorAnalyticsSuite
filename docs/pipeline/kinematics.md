# Subject kinematics

Step 4 of the analysis pipeline. It computes how each subject moves from frame to frame, and summarizes each track in a few numbers. The interface normally runs it on the trajectories confirmed in Step 3.

## Which points are used

Only detected points are used. Predicted placeholders, where the tracker held a track in place for lack of a detection, are skipped. A gap in a track is therefore bridged by one longer step between the detections on either side of it, and the time for that step is the full gap.

Points drawn or interpolated in the trajectory editor are saved as ordinary detected points, so they are included.

## Per-point measures

For each detected point after the first, comparing it with the previous detected point:

- **dx, dy** — change in position, in pixels.
- **displacement** — straight-line distance, `√(dx² + dy²)`.
- **speed** — displacement divided by the time between the two points.
- **heading** — direction of the step, `atan2(dy, dx)` in degrees from -180 to 180. 0° points right and 90° points down the image. Empty if the subject did not move.
- **acceleration** — from the third point on: the size of the change in velocity between the last two steps, divided by the mean of their durations. It is a magnitude, so a subject turning at constant speed also has acceleration.

Time is in seconds when a frame rate is given, and in frames otherwise. Units follow: px/s and px/s², or px/frame and px/frame².

## Per-track summaries

| Metric | Meaning |
|---|---|
| `total_distance_px` | Sum of all steps |
| `net_displacement_px` | Distance from the first point to the last |
| `path_straightness` | Net displacement divided by total distance, from 0 (wandering) to 1 (straight line) |
| `mean_speed`, `max_speed` | Over all steps |
| `mean_acceleration`, `max_acceleration` | Over all steps with an acceleration |

Each summary value is stored as a metric result, with the track's label in `value_json["track_label"]`.

## Output

- A CSV with the columns `track_id`, `frame`, `timestamp_ms`, `x`, `y`, `dx`, `dy`, `displacement_px`, `speed`, `acceleration` and `heading_deg`. Values that do not exist for a point, such as speed on a track's first point, are left empty.
- A `subject_kinematics` dataset holding it, with `origin` set to `derived`.
- The summary metrics described above.

## Code

- `app.tracking.kinematics`. See the [tracking reference](../reference/tracking.md).
- `app.jobs.subject_kinematics_job`. See the [jobs reference](../reference/jobs.md).
