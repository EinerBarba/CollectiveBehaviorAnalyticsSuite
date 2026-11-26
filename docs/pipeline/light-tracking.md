# Light tracking

Step 1 of the analysis pipeline. It describes where the rotating light stimulus is in every frame. It also records the circle the light moves on, which **later steps use as the arena**: the collective-behavior analysis takes its arena center and radius from this step, not from arena detection in Step 2. Every video therefore needs a light-tracking run, including videos with no stimulus.

## Calibrated mode

The light is assumed to move around a perfect circle at a constant speed. The researcher provides, in the interface:

- the circle's **center** and **radius**, in pixels;
- the light's **position at one frame**, the reference frame;
- how many **frames per rotation** the light takes;
- the **direction**: 1 or -1.

From these, the light's angle at the reference frame is `atan2(y − center_y, x − center_x)`. Every frame adds a constant step of `2π / frames_per_rotation` radians, signed by the direction. Frames before the reference frame are extrapolated backwards. The position in each frame is the point on the circle at that angle.

Image coordinates have y pointing down, so direction 1 (increasing angle) appears **clockwise** on screen.

## No-stimulus mode

If no reference position is given, the video is treated as having no stimulus. Every frame gets position (-1, -1), which the rest of the system reads as "light not present". The circle's center and radius are still recorded, because they define the arena.

## Output

- A CSV with one row per frame of the video, so its `frame` column matches the video's own frame numbers. Its columns are `frame`, `timestamp_ms`, `x`, `y`, `theta_rad`, `unwrapped_angle_rad` and `instantaneous_omega_rad_s`. In calibrated mode, `theta_rad` and `unwrapped_angle_rad` both hold the continuous angle, which keeps growing past 2π.
- A `trajectory_positions` dataset holding the CSV, and one `Track` row covering the whole video.
- Metric results for the circle's center and radius and, with a stimulus, the rotation period, angular velocity (in rad/s and deg/s), angular displacement and number of revolutions.
- The run's settings, which keep the calibration. Later steps read the center, radius, reference frame and rotation length from here.

## How later steps use it

- **Collective behavior** converts the calibration into the light's speed in degrees per frame, `360 / frames_per_rotation × direction`, and its angle at frame 0. These give the stimulus alignment measure S. A video whose light-tracking run has a reference frame counts as a stimulus video.
- **Position import** uses the center to convert imported coordinates into pixels.

## Importing instead

Light positions tracked by another tool can be imported from CSV instead. The circle, angles and speed are then derived from the positions. See [Data import](import.md).

## Code

- `app.cv.manual_tracking` computes the trajectory. See the [detection and light reference](../reference/cv.md).
- `app.jobs.manual_tracking_job` runs it and records the result. See the [jobs reference](../reference/jobs.md).
