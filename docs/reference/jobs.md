# Jobs reference

The background job behind each pipeline step. Private helper functions are shown here too, because much of each job's logic lives in them. For the pattern every job follows, see [Background jobs](../jobs.md).

::: app.jobs.manual_tracking_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$"]

::: app.jobs.subject_detection_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$"]

::: app.jobs.positional_tracking_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$"]

::: app.jobs.subject_kinematics_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$"]

::: app.jobs.collective_behavior_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$", "!^log$", "!^run_collective_behavior_job$", "!^_run_analysis$", "!^TOOL_VERSION_LABEL$"]

::: app.jobs.csv_import_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$"]

::: app.jobs.light_csv_import_job
    options:
      filters: ["!^__", "!^_[A-Z_]+$"]
