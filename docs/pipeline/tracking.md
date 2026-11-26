# Subject tracking

Step 3 of the analysis pipeline. It turns the per-frame subject detections from Step 2 into one continuous trajectory per subject. It works in two stages: an automatic pass that links detections into track fragments, and an interactive editor where the researcher assembles and corrects them.

## Stage 1: automatic linking

The tracker processes the frames in order. For each frame it decides which existing track each detection belongs to.

- **Matching.** Active tracks are paired with the frame's detections using the Hungarian algorithm, which finds the pairing with the smallest total distance between each track's last position and its matched detection.
- **Distance limit.** A pair farther apart than the maximum distance cannot be matched. These pairs are made prohibitively expensive before solving, so an out-of-range detection can never take the place of a valid, closer match.
- **New tracks.** A detection that matches no track starts a new one.
- **Missed frames.** A track with no matching detection stays where it was last seen. The placeholder position is stored and flagged as predicted. The track ends once it has gone unmatched for more than the allowed number of frames.
- **No motion model.** The tracker does not use velocity to predict where a subject will go next. A track is assumed to stay put until a detection appears nearby. Two subjects that cross paths can therefore swap identities, which is one reason Stage 2 exists.
- **Subject limit.** If the researcher sets the number of subjects, no more than that many tracks are ever created.

### Settings

- **Maximum distance** is the farthest, in pixels, a subject may move between frames and still be matched. The interface starts at 25 and the API default is 50.
- **Maximum missed frames** is how long a track survives without a match. The default is 5.
- **Number of subjects** is optional. Leaving it empty removes the limit.

### Output

The result is a CSV file with one row per track point and the columns `track_id`, `frame`, `timestamp_ms`, `x`, `y` and `is_predicted`. It is stored as a new dataset of type `trajectory_positions`, and the run records its inputs and parameters so the result can be traced.

Tracks that ended after missing frames keep their predicted placeholders. A track still active at the end of the video drops trailing predicted points, so it does not extend past the last real detection.

## Stage 2: interactive correction

The automatic pass usually produces more fragments than subjects. The editor helps the researcher assemble them into one complete trajectory per subject.

- **Automatic sorting.** The editor first creates one trajectory box per subject. It starts each with a track that begins near the start of the video and chains on the tracks that start after the previous one ends. Anything left over goes to an Unassigned pool.
- **Assign and move.** Tracks are dragged between trajectories and the Unassigned pool. They can also be dragged onto their marker in the video.
- **Split.** A track can be cut at the current frame, for example where it jumped from one subject to another.
- **Lock.** A trajectory marked as correctly finished is frozen. It cannot be edited, and it is skipped when new tracks are generated.
- **Missing segments.** A gap of about one second or more is flagged, at the start, in the middle or at the end of a trajectory, or over the whole video. The researcher fills it by drawing the subject's path in a mini video player. Simple mode places positions by clicking. Advanced mode records the cursor while the video plays at 1x, 2x or 4x, with a two-frame correction for reaction delay.

### Iterating

One automatic pass rarely finishes every trajectory, so the work is repeated.

1. The researcher selects **Generate Next Tracks**.
2. The tracker runs again on the detections not yet used by any track. A detection counts as used if it is within 6 pixels of an existing track point.
3. It looks for as many new tracks as there are unlocked trajectories that still end with missing frames. A new track needs several consecutive detections before it is accepted.
4. The new tracks appear in a separate pool, tagged with their iteration number. An optional minimum length sends very short ones to Unassigned.
5. The researcher drags each one into its trajectory or discards it, then repeats until every trajectory is complete.

### Saving and confirming

- **Save Progress** stores a snapshot at any time: the assignments, locks, pending tracks, iteration numbers and any split or drawn tracks. It is kept as a separate file version tied to the tracking result it came from, and can be reloaded later.
- **Confirm Trajectories** merges each trajectory's tracks frame by frame, preferring detected points over predicted ones, and fills short gaps by straight-line interpolation. It renumbers the tracks 1 to N, one per trajectory, and saves the result as a new version of the tracking file. The original automatic output stays in the version history.

Subject Kinematics and the collective-behavior analysis read the confirmed version.
