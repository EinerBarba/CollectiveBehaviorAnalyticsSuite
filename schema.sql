CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enums

DO $$ BEGIN
  CREATE TYPE role_scope AS ENUM ('global', 'laboratory', 'experiment');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE experiment_status AS ENUM ('planned', 'active', 'completed', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE file_type AS ENUM ('video', 'csv', 'json', 'image', 'model', 'log', 'archive', 'other');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE dataset_origin AS ENUM ('manual', 'automatic', 'derived', 'imported');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE dataset_status AS ENUM ('draft', 'valid', 'invalid', 'superseded');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE run_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE artifact_type AS ENUM ('file_version', 'dataset_version', 'model_version');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE prediction_type AS ENUM ('behavior_classification', 'anomaly_detection', 'regression', 'other');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE assignment_type AS ENUM ('automatic', 'manual');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE session_status AS ENUM ('draft', 'finalized');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE metric_value_type AS ENUM ('scalar', 'vector', 'json');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE metric_scope AS ENUM ('individual', 'group');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- Main

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  full_name text NOT NULL,
  password_hash text NOT NULL,
  is_system_admin boolean NOT NULL DEFAULT false,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  family_id uuid NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  replaced_by uuid REFERENCES refresh_tokens(id),
  user_agent text,
  ip_address text
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_family_id ON refresh_tokens(family_id);

CREATE TABLE IF NOT EXISTS laboratories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text UNIQUE NOT NULL,
  display_name text NOT NULL,
  applicable_scope role_scope NOT NULL,
  description text
);

CREATE TABLE IF NOT EXISTS role_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  role_id uuid NOT NULL REFERENCES roles(id),
  scope_type role_scope NOT NULL,
  scope_id uuid,
  granted_by uuid NOT NULL REFERENCES users(id),
  granted_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);

-- EXPERIMENTS / SUBJECTS

CREATE TABLE IF NOT EXISTS experiments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  laboratory_id uuid NOT NULL REFERENCES laboratories(id),
  title text NOT NULL,
  description text,
  study_subject_type text,
  status experiment_status NOT NULL DEFAULT 'planned',
  start_date date,
  end_date date,
  location text,
  environment_metadata jsonb,
  config_metadata jsonb,
  notes text,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS subjects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  laboratory_id uuid NOT NULL REFERENCES laboratories(id),
  species text,
  external_identifier text,
  label text NOT NULL,
  metadata jsonb,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS experiment_subjects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  subject_id uuid NOT NULL REFERENCES subjects(id),
  role_in_experiment text,
  added_by uuid NOT NULL REFERENCES users(id),
  added_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subject_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  name text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subject_group_members (
  subject_group_id uuid NOT NULL REFERENCES subject_groups(id),
  experiment_subject_id uuid NOT NULL REFERENCES experiment_subjects(id),
  PRIMARY KEY (subject_group_id, experiment_subject_id)
);

CREATE TABLE IF NOT EXISTS experiment_phases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  phase_type text NOT NULL,
  label text,
  start_time timestamptz,
  end_time timestamptz,
  sequence_order int,
  notes text
);

-- FILES / DATASETS

CREATE TABLE IF NOT EXISTS files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid REFERENCES experiments(id),
  file_type file_type NOT NULL,
  logical_name text NOT NULL,
  description text,
  is_raw boolean NOT NULL DEFAULT false,
  current_version_id uuid,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS file_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id uuid NOT NULL REFERENCES files(id),
  version_number int NOT NULL,
  storage_bucket text NOT NULL,
  storage_key text NOT NULL,
  mime_type text,
  size_bytes bigint NOT NULL,
  checksum_sha256 text NOT NULL,
  uploaded_by uuid NOT NULL REFERENCES users(id),
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  is_current boolean NOT NULL DEFAULT true
);

DO $$ BEGIN
  ALTER TABLE files
    ADD CONSTRAINT fk_files_current_version FOREIGN KEY (current_version_id) REFERENCES file_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS dataset_types (
  key text PRIMARY KEY,
  display_name text NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  dataset_type text NOT NULL REFERENCES dataset_types(key),
  name text NOT NULL,
  description text,
  origin dataset_origin NOT NULL,
  is_ground_truth boolean NOT NULL DEFAULT false,
  status dataset_status NOT NULL DEFAULT 'draft',
  current_version_id uuid,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS dataset_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id uuid NOT NULL REFERENCES datasets(id),
  version_number int NOT NULL,
  schema_version text,
  changelog text,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  is_current boolean NOT NULL DEFAULT true
);

DO $$ BEGIN
  ALTER TABLE datasets
    ADD CONSTRAINT fk_datasets_current_version FOREIGN KEY (current_version_id) REFERENCES dataset_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS dataset_spatial_metadata (
  dataset_version_id uuid PRIMARY KEY REFERENCES dataset_versions(id),
  coordinate_system text,
  sampling_rate_hz numeric,
  units text,
  frame_start int,
  frame_end int
);

CREATE TABLE IF NOT EXISTS dataset_files (
  dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  file_version_id uuid NOT NULL REFERENCES file_versions(id),
  role text NOT NULL DEFAULT 'primary',
  PRIMARY KEY (dataset_version_id, file_version_id)
);

-- TOOLS / MODELS / PROCESSING

CREATE TABLE IF NOT EXISTS tools (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  category text NOT NULL,
  description text
);

CREATE TABLE IF NOT EXISTS tool_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tool_id uuid NOT NULL REFERENCES tools(id),
  version_label text NOT NULL,
  commit_hash text,
  container_image text,
  released_at timestamptz
);

CREATE TABLE IF NOT EXISTS models (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  laboratory_id uuid NOT NULL REFERENCES laboratories(id),
  name text NOT NULL,
  model_type text NOT NULL,
  description text,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processing_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  tool_version_id uuid NOT NULL REFERENCES tool_versions(id),
  model_version_id uuid,
  initiated_by uuid NOT NULL REFERENCES users(id),
  status run_status NOT NULL DEFAULT 'queued',
  parameters jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  error_message text,
  runtime_info jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id uuid NOT NULL REFERENCES models(id),
  version_label text NOT NULL,
  hyperparameters jsonb,
  artifact_file_version_id uuid REFERENCES file_versions(id),
  training_run_id uuid REFERENCES processing_runs(id),
  is_deprecated boolean NOT NULL DEFAULT false,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
  ALTER TABLE processing_runs
    ADD CONSTRAINT fk_processing_runs_model_version FOREIGN KEY (model_version_id) REFERENCES model_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS processing_run_inputs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  processing_run_id uuid NOT NULL REFERENCES processing_runs(id),
  artifact_type artifact_type NOT NULL,
  file_version_id uuid REFERENCES file_versions(id),
  dataset_version_id uuid REFERENCES dataset_versions(id),
  model_version_id uuid REFERENCES model_versions(id),
  role text NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_run_outputs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  processing_run_id uuid NOT NULL REFERENCES processing_runs(id),
  artifact_type artifact_type NOT NULL,
  file_version_id uuid REFERENCES file_versions(id),
  dataset_version_id uuid REFERENCES dataset_versions(id),
  model_version_id uuid REFERENCES model_versions(id),
  role text NOT NULL DEFAULT 'primary_output'
);

CREATE TABLE IF NOT EXISTS model_evaluations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id uuid NOT NULL REFERENCES model_versions(id),
  dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  processing_run_id uuid REFERENCES processing_runs(id),
  metric_name text NOT NULL,
  metric_value double precision NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_predictions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id uuid NOT NULL REFERENCES model_versions(id),
  processing_run_id uuid NOT NULL REFERENCES processing_runs(id),
  dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  experiment_subject_id uuid REFERENCES experiment_subjects(id),
  prediction_type prediction_type NOT NULL,
  frame_number int,
  timestamp_ms bigint,
  predicted_label text,
  confidence double precision,
  extra jsonb
);

CREATE TABLE IF NOT EXISTS tracks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  processing_run_id uuid NOT NULL REFERENCES processing_runs(id),
  track_label text NOT NULL,
  start_frame int NOT NULL,
  end_frame int NOT NULL,
  confidence_avg double precision,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identity_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  track_id uuid NOT NULL REFERENCES tracks(id),
  experiment_subject_id uuid NOT NULL REFERENCES experiment_subjects(id),
  assignment_type assignment_type NOT NULL,
  confidence double precision,
  assigned_by_user uuid REFERENCES users(id),
  assigned_by_run uuid REFERENCES processing_runs(id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  is_current boolean NOT NULL DEFAULT true,
  superseded_by uuid REFERENCES identity_assignments(id)
);

CREATE TABLE IF NOT EXISTS manual_annotation_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  source_file_version_id uuid NOT NULL REFERENCES file_versions(id),
  experiment_subject_id uuid REFERENCES experiment_subjects(id),
  status session_status NOT NULL DEFAULT 'draft',
  finalized_dataset_version_id uuid REFERENCES dataset_versions(id),
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS annotation_points (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES manual_annotation_sessions(id),
  frame_number int NOT NULL,
  timestamp_ms bigint,
  x double precision NOT NULL,
  y double precision NOT NULL,
  is_estimated boolean NOT NULL DEFAULT false,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS metric_definitions (
  key text PRIMARY KEY,
  display_name text NOT NULL,
  unit text,
  value_type metric_value_type NOT NULL,
  scope metric_scope NOT NULL
);

CREATE TABLE IF NOT EXISTS metric_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  processing_run_id uuid NOT NULL REFERENCES processing_runs(id),
  metric_key text NOT NULL REFERENCES metric_definitions(key),
  experiment_subject_id uuid REFERENCES experiment_subjects(id),
  subject_group_id uuid REFERENCES subject_groups(id),
  experiment_phase_id uuid REFERENCES experiment_phases(id),
  value_numeric double precision,
  value_json jsonb,
  computed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS comparison_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  reference_dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  candidate_dataset_version_id uuid NOT NULL REFERENCES dataset_versions(id),
  processing_run_id uuid NOT NULL REFERENCES processing_runs(id),
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS comparison_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  comparison_run_id uuid NOT NULL REFERENCES comparison_runs(id),
  experiment_subject_id uuid REFERENCES experiment_subjects(id),
  metric_name text NOT NULL,
  value_numeric double precision NOT NULL,
  frame_range_start int,
  frame_range_end int,
  extra jsonb
);

CREATE TABLE IF NOT EXISTS stimulus_types (
  key text PRIMARY KEY,
  display_name text NOT NULL
);

CREATE TABLE IF NOT EXISTS stimuli (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  experiment_id uuid NOT NULL REFERENCES experiments(id),
  stimulus_type text NOT NULL REFERENCES stimulus_types(key),
  description text,
  configuration jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stimulus_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stimulus_id uuid NOT NULL REFERENCES stimuli(id),
  experiment_phase_id uuid REFERENCES experiment_phases(id),
  start_time timestamptz NOT NULL,
  end_time timestamptz,
  position_x double precision,
  position_y double precision,
  trajectory_dataset_version_id uuid REFERENCES dataset_versions(id),
  speed double precision,
  direction double precision,
  intensity double precision
);
