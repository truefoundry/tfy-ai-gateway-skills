---
name: jobs
description: Job run failed, stuck, never triggered, cron not firing, retries exhausted, no pods for a job. Read for application type job (or when the user says job/cron/run failed).
---

Jobs are not long-running services. Debug against a **specific run**, not only the application definition.

## Triage

1. Confirm `type: job` from `get_application`.
2. `list_job_runs` — pick the failing/latest run; note `jobRunName` / id and status.
3. `get_job_run` for that run.
4. `get_logs` with `jobRunName` set (and time window around the run).
5. `list_application_events` with the same `jobRunName` (do **not** also pass `podNames`).
6. If the run created pods: `list_k8s_pods` + same crash/pending playbooks as services (`failure-modes/crashloop-oom-probes.md`, `pending-scheduling.md`).

## Status reading

| Observation | Meaning |
|---|---|
| No runs at all | Trigger/cron/manual run never fired — check schedule, pause state, permissions to trigger |
| Run `FAILED` with pods | Same as service failure modes on those pods |
| Run failed with no pods | Often schedule/quota/validation — events + deployment status |
| Run succeeded but user expected new code | Build dedup / old image — `builds.md` |
| Retries looping | Backoff; fix root cause in logs rather than raising retry count blindly |

## Cron / schedule

If "job did not run today": verify the application is not paused (`pause_application` state), the cron expression/timezone, and cluster agent health (`get_cluster_status`). Lack of a run is not proven by empty pod lists alone.

## Checklist

- [ ] Did I pin a specific `jobRunName` before fetching logs/events?
- [ ] Did I avoid combining `jobRunName` and `podNames` on events?
- [ ] If pods exist, did I reuse the service failure-mode playbooks?
- [ ] If no runs exist, did I investigate trigger/schedule/pause rather than CrashLoop?

For more info: `search_docs` with "jobs", "job runs", "cron".
