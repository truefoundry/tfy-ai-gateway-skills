---
name: teams
description: Create and manage teams — groups of users that can be used for access control, rate limiting, and budget scoping.
---

**Teams** are groups of users used for access control and policy scoping across the platform. Granting a team access to a resource automatically grants access to all its members.

Note: There is an implicit `everyone` team which includes all users in the tenant (but not virtual accounts).

## Fetching existing teams

Use the `list_teams` tool to get the list of all teams. Use `get_team` to inspect a single team by name or ID.

## Creating Teams (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `team`.

### Phase 2: Build and Validate

1. Collect the team name and member emails from the user.
2. Build the manifest following the JSON schema strictly. Write it to a file.
3. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
4. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
5. If dry-run fails, fix and retry.
6. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to create the team.

### Manifest Structure

```yaml
type: team
name: <unique-team-name>
members:
  - <user-email-1>
  - <user-email-2>
```

### Checklist

- [ ] Called `get_manifest_json_schema` with type `team`?
- [ ] Validated with `scripts/validate_schema.py`?
- [ ] Dry-run with `apply_manifest` (dryRun: true) passed?
- [ ] Applied with `apply_manifest` (direct tool call, not sandbox)?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about teams.
Search terms: "team management", "create team", "team access control", "SSO group sync"
