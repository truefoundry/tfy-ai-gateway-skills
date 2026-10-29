---
name: jobs
description: Job run failed, stuck, never triggered, cron not firing, retries exhausted, no pods for a job. Read for application type job (or when the user says job/cron/run failed).
---

Jobs are not long-running services. Debug against a **specific run**, not only the application definition.

## Triage

`type: job` is known from `troubleshooting.md` Phase 1.

1. `list_job_runs` (path `jobId` = application `id`; filter `status: ["FAILED"]` when looking for failures). Runs come newest first with `name`, `status`, `error`, `exitCode`, `totalRetries`. Skip `get_job_run` — it adds nothing for triage.
2. In one message, for the chosen run `name` as `jobRunName`: `get_logs(applicationId, jobRunName, direction="desc", limit=200)` and `list_application_events(applicationId, jobRunName)` (do **not** also pass `podNames` — rejected). Add a `startTs` around the run's `createdAt` when it is older than a day.
3. If the run created pods: `get_application_state` + the same crash/pending playbooks as services (`failure-modes/crashloop-oom-probes.md`, `failure-modes/pending-scheduling.md`).

## Status reading

Run statuses: `CREATED`, `SCHEDULED`, `RUNNING`, `FINISHED` (succeeded), `FAILED`, `TERMINATION_REQUESTED`, `TERMINATING`, `TERMINATED`, `UNKNOWN`.

| Observation | Meaning |
|---|---|
| No runs at all | Trigger/cron/manual run never fired — check schedule, pause state, permissions to trigger |
| Run `FAILED` with pods | Same as service failure modes on those pods |
| Run failed with no pods | Often schedule/quota/validation — events + deployment status |
| Run `FINISHED` but user expected new code | Build dedup / old image — `builds.md` |
| Retries looping | Backoff; fix root cause in logs rather than raising retry count blindly |

## Cron / schedule

If "job did not run today": verify the application is not paused (`get_application` → `metadata.paused`), the cron expression/timezone, and that tfy-agent is publishing (`get_application_state`, see `failure-modes/rollout-argocd.md`). Lack of a run is not proven by empty pod lists alone.

## Checklist

- [ ] Did I pin a specific `jobRunName` before fetching logs/events?
- [ ] Did I avoid combining `jobRunName` and `podNames` on events?
- [ ] If pods exist, did I reuse the service failure-mode playbooks?
- [ ] If no runs exist, did I investigate trigger/schedule/pause rather than CrashLoop?

For more info: `search_docs` with "jobs", "job runs", "cron".
