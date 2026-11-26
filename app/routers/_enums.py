from typing import Literal

RoleScope = Literal["global", "laboratory", "experiment"]
ExperimentStatus = Literal["planned", "active", "completed", "archived"]
FileType = Literal["video", "csv", "json", "image", "model", "log", "archive", "other"]
DatasetOrigin = Literal["manual", "automatic", "derived", "imported"]
DatasetStatus = Literal["draft", "valid", "invalid", "superseded"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ArtifactType = Literal["file_version", "dataset_version", "model_version"]
PredictionType = Literal["behavior_classification", "anomaly_detection", "regression", "other"]
AssignmentType = Literal["automatic", "manual"]
SessionStatus = Literal["draft", "finalized"]
MetricValueType = Literal["scalar", "vector", "json"]
MetricScope = Literal["individual", "group"]
