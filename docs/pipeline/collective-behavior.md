# Collective behavior

The final step of the analysis pipeline, run once per experiment over all its videos. It describes how the group as a whole behaves over time, finds recurring behavioral **states**, and models how the group moves between them. It works in four stages: windows, order parameters, states and transitions.

## 1. Windows

Each video's frames are cut into overlapping **windows**. By default a window is 100 frames long and a new one starts every 50 frames, so neighboring windows share half their frames. Only whole windows are used, so the last few frames of a video may not be analyzed.

A window is skipped if:

- fewer than half of its expected points were detected. The expected count is the window's group size, **N** (the most subjects detected in any of its frames), times its length;
- it has no usable headings;
- for stimulus videos, it starts before the light first appears.

Windows with N below 5 are kept and measured but **excluded from clustering**.

## 2. Order parameters

Each subject's **heading** in a frame is the direction of its step from its previous detected point, as a unit vector. Predicted points are skipped, and steps of zero length have no heading. Because headings are unit vectors, speed plays no part in any measure below.

Each measure is computed per frame from all subjects with a heading, then averaged over the window's frames.

### P — polarization

How much the subjects move in the same direction. It is the length of the average heading vector:

```
P = | mean of all subjects' headings |
```

1 means everyone moves the same way; values near 0 mean there is no shared direction. With few subjects, P is somewhat above 0 even for random headings.

### P_local — local polarization

Polarization within parts of the arena. The arena is split into 8 equal angular sectors around its center (45° each). For each occupied sector, P is computed from the subjects in it, or set to 0 if only one subject is there. P_local is the mean over the occupied sectors. It can be high when separate groups each move coherently in different directions, which would make P low.

### M — milling

How much the subjects circle around the arena center. For each subject, with position `r` relative to the center and heading `u`:

```
m = (r × u) / arena_radius = (rx·uy − ry·ux) / arena_radius
```

This is positive when circling one way and negative the other way, and largest at the wall moving along it. **M** is the absolute value of the frame's mean, so it measures circling in either direction. **M_signed** keeps the sign and is stored but not used for clustering.

### S — stimulus alignment

How closely the group follows the light. Only computed for stimulus videos. The light's angular position in a frame is

```
theta_light = theta_light_0 + omega × frame
```

with `omega` in degrees per frame. The target direction is the light's direction of travel at that position, `theta_light + 90°` in the direction of rotation. S is the cosine of the angle between the group's average heading and that target:

- **1** — the group moves the way the light moves;
- **0** — at right angles to it;
- **-1** — the opposite way.

It is one direction for the whole group, not relative to each subject's own position. For clustering, S is rescaled to 0 to 1 as `S_normalized = (S + 1) / 2`.

## 3. States

Windows are treated as points in feature space and grouped with a **Gaussian mixture model**:

- **Features.** P, P_local, M and S_normalized with a stimulus; P, P_local and M without.
- **Fitting.** Models with 2, 3, 4 and 5 components are fitted, each with full covariance, 10 random restarts and a fixed random seed, so results are repeatable.
- **Choosing the number of states.** The model with the lowest **BIC** (Bayesian information criterion), which balances fit against complexity, is kept.
- **Labeling.** Every window is labeled with its most likely state. The probability of each state and an **assignment entropy** are kept too; entropy near 0 means the window clearly belongs to one state.
- **Numbering.** Components come out in arbitrary order, so states are renumbered by the mean of one feature, lowest first: by **P**, so state 0 is the least polarized.

A state is a region of feature space, not a behavior in itself. Naming states, for example "milling" or "following", is an interpretation the researcher makes from their mean values.

## 4. Transitions

The sequence of state labels is treated as a **first-order Markov chain**: the next state depends only on the current one.

- **Transition matrix.** Counts of moves from each state to each state, between consecutive clustered windows of the same video, turned into probabilities per row. Every count starts at 1, so no transition has probability exactly 0. Windows skipped earlier do not break the sequence, and videos are never joined to each other.
- **Stationary distribution.** The long-run share of time in each state implied by the matrix.
- **Mean dwell time.** The expected time spent in a state once entered, `1 / (1 − p)` window steps, where `p` is the chance of staying. This assumes dwell times are geometrically distributed.
- **Dwell runs.** The actual observed stays: each run of identical consecutive labels, with its length.

Window steps are converted to seconds with the frame rate.

## Running the analysis

The analysis is run from the experiment's Collective Behavior Analysis tab, by `run_collective_behavior_experiment_job`. It:

1. Finds every video in the experiment with a succeeded light-tracking run and a succeeded tracking run, using the newest of each. The trajectories are read from the current version of the tracking run's output file, so trajectories confirmed in the editor are used rather than the automatic output.
2. Takes the arena center and radius, the frame rate and the stimulus from the light-tracking run. A calibrated light gives `omega = 360 / frames_per_rotation × direction` degrees per frame. An imported light counts as a stimulus if its mean angular velocity is above 0.01 rad/s.

    The light trajectory counts frames at its own rate: the video's rate for a calibration, the import rate for a light CSV. The tracks count detection samples, which are every *frame step*-th video frame from the start frame. The job finds the detection run behind each tracking run and lines the two up in time. Sample `s` is at `(start + s × step) / native_fps` and light frame `f` is at `f / light_fps`. It rescales `omega`, the light's starting angle and the switch-on frame to match.
3. Splits the videos into **stimulus** and **no-stimulus** conditions and pools each condition's windows.
4. Fits a separate mixture and Markov model per condition. States are therefore defined separately in each condition: state 1 under stimulus need not resemble state 1 without it.

It accepts optional settings: a frame-rate override, a **frame step** to simulate a lower frame rate, and the window size and step.

## Output

Each condition saves six files in a `collective_behavior_windows` dataset. Each name has the condition as a suffix, for example `windows_stimulus.parquet`.

| File | Contents |
|---|---|
| `windows.parquet` | Every window's order parameters, state, state probabilities and entropy |
| `gmm_model.pkl` | The chosen fitted model |
| `bic_scores.csv` | BIC and AIC for each number of states tried |
| `transition_matrix.csv` | The transition probabilities |
| `markov_summary.json` | Stationary distribution, mean dwell times, counts, the transition matrix and each state's mean P, M and S |
| `dwell_runs.parquet` | Every observed stay in a state |

Headline values are also stored as metrics: the number of states, mean P, M and S, and the number of clustered windows. They are named `cb_experiment_<metric>_<condition>`.

## Code

- `app.analysis.order_parameters`, `app.analysis.clustering` and `app.analysis.markov`. See the [analysis reference](../reference/analysis.md).
- `app.jobs.collective_behavior_job`. See the [jobs reference](../reference/jobs.md).
