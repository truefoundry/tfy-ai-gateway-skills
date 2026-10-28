---
name: audit-logs
description: Read for who created, changed or deleted something, what a user or virtual account did, when access was granted or revoked, and questions about audit logs themselves (what is recorded, who can read them, retention).
---

Audit logs record changes on the platform: one entry per action, newest first. Read them with `get_audit_logs`; `get_audit_log_actions` lists the action names.

## What is recorded

- Successful creates, updates and deletes (applying a manifest, deleting an entity), access grants and revokes, team membership, user changes, application operations (pause, resume, trigger a job), and token or secret views (`GET_TOKEN`, `VIEW_SECRET`).
- Not recorded: failed or forbidden requests, dry runs, other reads, and gateway LLM or MCP requests (those are traces: `observability.md`). "No entry" never means "nobody tried".
- TrueFoundry does not delete entries.

Each entry has `action`, `resourceType`, `resourceName`, `resourceFqn`, `resourceId`, `subject` (who: `subjectSlug` is the email or virtual account name, `subjectType`, and `subjectPatName` when they used a personal access token), `createdAt`, `message` (a one-line summary) and `metaData.public`, which usually holds `manifest` and `previousManifest`. Credentials in those manifests are partially masked. `eventSourceMetadata` has the client IP and user agent.

## Who can read them

The caller needs the tenant permission Read Audit Logs: tenant admins have it, and a custom role can include `tenant:ReadAuditLogs` (`access-management.md` → Custom roles). Without it, both tools return 403; on a plan without audit logs, `get_audit_logs` returns 402. Say which, and don't try another way to read them.

## Query

1. Get `get_current_datetime`'s result, then always set `start` and `end` (ISO 8601). If the user gave no range, use the last 7 days and say so.
2. Filter with the most specific fields you have:
   - `resourceType` with `resourceName` (or `resourceFqn`, `resourceId`) for "who changed X". Virtual accounts and personal access tokens are `service-account`; ML repos are `mlf-project`. A grant or revoke is filed under the resource it is on (`tenant` for tenant roles).
   - `subjectSlug` for "what did Y do": an email, or a virtual account name.
   - `action` (comma separated) for a kind of change. Take names from `get_audit_log_actions`, never guess, and include every name that fits: a change to one entity type can be `APPLY_`, `CREATE_`, `UPDATE_` or `CREATE_OR_UPDATE_` plus the type, and deletes are `DELETE_` plus the type.
   - `search` matches message, action, resource name and FQN, but is slow; use it only when nothing above fits.
3. For "how many", pass `metric: count` and read `pagination.total`.
4. List from the sandbox: entries are large (up to ~14 KB each, as they carry both manifests), so even a few overflow the result limit. One program calls `call_tool("<server>", "get_audit_logs", start=..., end=..., limit=50, ...)` on the Code Mode server hosting the tool, pages with `offset` while `pagination.total` is larger, and prints only `createdAt`, `action`, `resourceType`/`resourceName`, `subject.subjectSlug` (and `subjectPatName`), and `message`.
5. For "what exactly changed" in one entry, print the difference between `metaData.public.previousManifest` and `manifest` for that entry only.

Show times in the user's timezone if known, otherwise UTC, and name the subject as recorded. Show IPs only when asked.

UI: `{controlPlaneUrl}/access-management?tab=audit-logs`. Docs: [audit logging](https://www.truefoundry.com/docs/platform/audit-logging).
