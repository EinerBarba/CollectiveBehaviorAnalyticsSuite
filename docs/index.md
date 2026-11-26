# Collective Behavior Analytics

A web-based system for tracking groups of subjects in top-down video and quantifying their collective behavior. It takes a raw recording through detection, tracking, kinematics and collective-behavior analysis, and stores every result with its version history so analyses can be traced and reproduced.

This site documents the **backend**: how it is organized, what each processing step computes, how data is stored, and the code behind it. The HTTP endpoints are documented separately by FastAPI at `/docs` on a running server, and the frontend is not covered here.

## The analysis pipeline

Each video moves through four steps, and the experiment's videos are then analyzed together in a fifth. Each step is a background job that reads the previous step's output and records its own.

1. **[Light tracking](pipeline/light-tracking.md).** Describes the rotating light stimulus, and the circle it moves on, for every frame.
2. **[Subject detection](pipeline/detection.md).** Finds the arena and the subjects in each frame.
3. **[Subject tracking](pipeline/tracking.md).** Links detections into tracks, then lets the researcher correct them.
4. **[Subject kinematics](pipeline/kinematics.md).** Computes displacement, speed, acceleration and heading.
5. **[Collective behavior](pipeline/collective-behavior.md).** Run once per experiment over all its videos. Computes order parameters, groups time windows into states and models the transitions between them.

Positions and light trajectories tracked elsewhere can be brought in instead of Steps 1 to 3. See [Data import](pipeline/import.md).

## How this site is organized

- **[Architecture](architecture.md)** gives the overall shape of the backend and a map of its modules.
- **[Background jobs](jobs.md)** explains the pattern every processing step follows.
- **Pipeline** has one page per step, in plain language: what it does, why, and what the settings mean.
- **[Data model](data-model.md)**, **[Storage](storage.md)** and **[Authentication](auth.md)** cover how data and access are handled.
- **Reference** pages are generated from the docstrings in the code and describe each module, class, function and constant.
