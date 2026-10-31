---
name: audit-logs
description: Read for who created, changed or deleted something, what a user or virtual account did, when access was granted or revoked, and questions about audit logs themselves (what is recorded, who can read them, retention).
---

Audit logs record changes on the platform: one entry per action, newest first. Read one resource with `get_resource_audit_logs`. Read the tenant with `get_audit_logs`. `get_audit_log_actions` lists the action names.

## What is recorded

- Successful creates, updates and deletes (applying a manifest, deleting an entity), access grants and revokes, team membership, user changes, application operations (pause, resume, trigger a job), and token or secret views (`GET_TOKEN`, `VIEW_SECRET`).
- Not recorded: failed or forbidden requests, dry runs, other reads, and gateway LLM or MCP requests (those are traces: `observability.md`). "No entry" never means "nobody tried".
- TrueFoundry does not delete entries.

Each entry has `action`, `resourceType`, `resourceName`, `resourceFqn`, `resourceId`, `subject` (who: `subjectSlug` is the email or virtual account name, `subjectType`, and `subjectPatName` when they used a personal access token), `createdAt`, `message` (a one-line summary) and `metaData.public`, which usually holds `manifest` and `previousManifest`. Credentials in those manifests are partially masked. `eventSourceMetadata` has the client IP and user agent.

## Who can read them

`get_audit_logs` and `get_audit_log_actions` need the tenant permission Read Audit Logs: tenant admins have it, and a custom role can include `tenant:ReadAuditLogs` (`access-management.md` → Custom roles). Without it they return 403; on a plan without audit logs, `get_audit_logs` returns 402.

`get_resource_audit_logs` needs neither that permission nor the plan feature. Access follows the resource: Read Audit Logs still allows it; otherwise the caller needs manage on that resource — manage on its workspace for an application or a deployment, Manage Users for a user or virtual account (`service-account`), Manage Roles for a role, Manage Gateway Configs for `gateway-config`, `gateway-budget` and `gateway-rate-limit`. A 403 means no permission, or the resource does not exist. Client IP is included only when the caller has Read Audit Logs. Say which refusal it was, and don't try another way to read them.

## One resource

For "who changed X" on a resource you can look up, call `get_resource_audit_logs` with `resourceType` and `resourceId` from that resource's get or list tool. Omit `resourceId` only for `gateway-budget` and `gateway-rate-limit` (every rule of that type; pass the id or `resourceName` to narrow to one). For `gateway-config`, `resourceName` is required and `resourceId` is optional. A cluster returns every entry in it; a workspace returns the workspace and activity inside it; other types return the resource and its children. It has no `subjectSlug` and no `metric`. Omit `action` unless you already know the name — `get_audit_log_actions` itself needs Read Audit Logs. A deleted resource has no id to look up; use `get_audit_logs` with `resourceName` for that. Same `start`/`end` and sandbox listing as below.

## Query

These steps are for `get_audit_logs` (what someone did, a count, an action across the tenant, a deleted resource).

1. Get `get_current_datetime`'s result, then always set `start` and `end` (ISO 8601). If the user gave no range, use the last 7 days and say so. Do the same for `get_resource_audit_logs`.
2. Filter with the most specific fields you have:
   - `resourceType` with `resourceName` (or `resourceFqn`, `resourceId`) when the resource tool does not apply. Virtual accounts and personal access tokens are `service-account`; ML repos are `mlf-project`. A grant or revoke is filed under the resource it is on (`tenant` for tenant roles).
   - `subjectSlug` for "what did Y do": an email, or a virtual account name.
   - `action` (comma separated) for a kind of change. Take names from `get_audit_log_actions`, never guess, and include every name that fits: a change to one entity type can be `APPLY_`, `CREATE_`, `UPDATE_` or `CREATE_OR_UPDATE_` plus the type, and deletes are `DELETE_` plus the type.
   - `search` matches message, action, resource name and FQN, but is slow; use it only when nothing above fits.
3. For "how many", pass `metric: count` and read `pagination.total`.
4. List from the sandbox: entries are large (up to ~14 KB each, as they carry both manifests), so even a few overflow the result limit. One program calls `call_tool` for the tool you chose (`get_audit_logs` or `get_resource_audit_logs`) with `start`, `end`, `limit=50` and its filters, on the Code Mode server hosting the tool, pages with `offset` while `pagination.total` is larger, and prints only `createdAt`, `action`, `resourceType`/`resourceName`, `subject.subjectSlug` (and `subjectPatName`), and `message`.
5. For "what exactly changed" in one entry, print the difference between `metaData.public.previousManifest` and `manifest` for that entry only.

Show times in the user's timezone if known, otherwise UTC, and name the subject as recorded. Show IPs only when asked.

UI: `{controlPlaneUrl}/access-management?tab=audit-logs`. Docs: [audit logging](https://www.truefoundry.com/docs/platform/audit-logging).
