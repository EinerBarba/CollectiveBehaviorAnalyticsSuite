"""PostgreSQL enum types used by the models.

The types themselves are created by `schema.sql` (`create_type=False`), so
adding a value means changing the database as well as this file.
"""

from sqlalchemy.dialects.postgresql import ENUM

role_scope = ENUM("global", "laboratory", "experiment", name="role_scope", create_type=False)
experiment_status = ENUM("planned", "active", "completed", "archived", name="experiment_status", create_type=False)
file_type_enum = ENUM("video", "csv", "json", "image", "model", "log", "archive", "other", name="file_type", create_type=False)
dataset_origin = ENUM("manual", "automatic", "derived", "imported", name="dataset_origin", create_type=False)
dataset_status = ENUM("draft", "valid", "invalid", "superseded", name="dataset_status", create_type=False)
run_status = ENUM("queued", "running", "succeeded", "failed", "cancelled", name="run_status", create_type=False)
artifact_type = ENUM("file_version", "dataset_version", "model_version", name="artifact_type", create_type=False)
prediction_type = ENUM(
    "behavior_classification", "anomaly_detection", "regression", "other", name="prediction_type", create_type=False
)
assignment_type = ENUM("automatic", "manual", name="assignment_type", create_type=False)
session_status = ENUM("draft", "finalized", name="session_status", create_type=False)
metric_value_type = ENUM("scalar", "vector", "json", name="metric_value_type", create_type=False)
metric_scope = ENUM("individual", "group", name="metric_scope", create_type=False)
