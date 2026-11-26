# Subject detection

Step 2 of the analysis pipeline. It finds the circular arena once, then the subjects in every sampled frame, as small bright spots inside the arena.

## Finding the arena

The arena (the plate) is found once per video from its first frames, unless the researcher sets it by hand in the interface.

1. **Preprocessing.** Bright objects, such as the subjects and the light, would create false edges, so pixels brighter than 80% of the frame's maximum are replaced with mid-gray. The contrast is then tripled around mid-gray, the result is clipped and stretched to the full brightness range, and the frame is converted to grayscale.
2. **Circle search.** The Hough circle transform looks for circles with a radius between 30% and 50% of the frame's shorter side. Circles that extend past the frame's edges are discarded.
3. **Choice.** Up to 30 frames are tried in order. The first frame that yields any circle wins, and its largest circle is taken as the arena.

If no circle is found in those frames, detection fails with an error. Setting the arena by hand avoids the search entirely.

## Finding subjects

For each sampled frame:

1. Everything outside the arena is blacked out.
2. The frame is converted to grayscale and lightly blurred (3×3 Gaussian) to reduce noise.
3. Pixels brighter than the **brightness ratio** times the frame's brightest pixel become foreground. The threshold is relative to each frame, so it adapts to overall lighting but also moves with the brightest object in view.
4. Each connected foreground region is a candidate blob. It counts as a subject only if it passes every filter:
    - **area** between the minimum and maximum, in square pixels;
    - **solidity** (area divided by the area of its convex hull) above the minimum, which rejects irregular shapes;
    - **aspect ratio** (width divided by height of its bounding box) within range, which rejects long thin shapes;
    - **circularity** (4π × area / perimeter²) above the minimum, which rejects jagged shapes.
5. Each accepted blob's position is its center, from its image moments, rounded down to whole pixels.

### Settings

| Setting | Default in the code | Meaning |
|---|---|---|
| Minimum area | 50 px² | Smallest blob counted |
| Maximum area | 250 px² | Largest blob counted |
| Brightness ratio | 0.85 | Threshold as a share of the frame's brightest pixel |
| Minimum solidity | 0.80 | From 0 to 1; 1 is a perfectly convex shape |
| Aspect ratio | 0.5 to 2.0 | Accepted width-to-height range |
| Minimum circularity | 0.50 | From 0 to 1; 1 is a perfect circle |

The interface can show different starting values; the ones it sends are recorded in the run's settings.

### Sampling frames

If the experiment's frame rate is set lower than the video's, the interface sends a **frame step**, and only one frame in every frame step is processed. The output is then keyed by **sample index** (0, 1, 2, …) rather than by the video's own frame number, and the reported frame rate is the video's rate divided by the frame step.

## Live preview

Before running detection, the interface shows a preview for one frame through `GET /videos/{id}/detection-analysis`. It runs the same steps but reports **every** blob, including rejected ones with the reason (too small, too large, not solid, wrong aspect, not circular), and returns the thresholded and annotated images. This lets the researcher tune the settings while seeing their effect.

## Output

- A JSON file mapping each frame key to a list of `[x, y]` positions.
- A `subject_detections` dataset holding it, with the effective frame rate and frame range as spatial metadata.
- In the run's `runtime_info`: the number of frames, the frame rate, the arena found, and the minimum, maximum and mean number of detections per frame. The mean is a quick check that the settings find about the right number of subjects.

## Code

- `app.cv.plate_detection` and `app.cv.subject_detection`. See the [detection and light reference](../reference/cv.md).
- `app.jobs.subject_detection_job`. See the [jobs reference](../reference/jobs.md).
