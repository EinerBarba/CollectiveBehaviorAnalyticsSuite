# Storage

Files are stored on local disk under the folder set by `STORAGE_ROOT`. The database holds each file's location, size and checksum, but never its contents.

## Layout

Everything is written under `STORAGE_ROOT/local/`. The part after `local/` is the **storage key** recorded on each file version.

| Path under `local/` | Contents |
|---|---|
| `videos/<file id>/<version><extension>` | Uploaded videos, one file per version |
| `thumbnails/<file version id>.jpg` | Video thumbnails, made after upload |
| `frames/<run id>/` | Exported frames and their `manifest.json` |
| `experiments/<experiment id>/processing-runs/<run id>/` | Every job's outputs |
| `experiments/<experiment id>/trajectory-edits/` | Confirmed trajectories from the editor |
| `experiments/<experiment id>/trajectory-progress/` | Editor progress saves |
| `experiments/<experiment id>/csv-imports/` | Files created by imports |

Outputs, edits, progress saves and imports are written by `storage.save_bytes`, which puts a random 32-character prefix in front of the file name, as in `3f9c…_positional_tracks.csv`. Saving the same name twice therefore never overwrites an earlier file.

## Integrity

- **Checksums.** Every stored file's SHA-256 checksum is recorded on its file version, so its contents can be verified later. Uploads are hashed as they are written.
- **Path checks.** Storage keys are resolved to absolute paths and rejected if they would point outside the storage root, for example through `..` segments.
- **No overwriting.** New results and corrections are always new files and new versions. Nothing in the pipeline changes a stored file in place.

## Deleting data

- **Soft delete** marks a row with `deleted_at` and leaves its files in place.
- **Deleting a video** is permanent and limited to system administrators (`DELETE /videos/{file id}`). It follows the provenance records outward from the video: every run that used one of its versions, everything those runs produced, the runs that used those outputs, and so on. It removes all of those records, then deletes the files from disk.
- **Failed jobs** roll back their database records but leave any files they had already written.

## Code

`app.storage`. See the [core reference](reference/core.md).
