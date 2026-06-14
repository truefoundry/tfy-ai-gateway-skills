---
name: teams
description: Create and manage teams — groups of users that can be used for access control, rate limiting, and budget scoping.
---

**Teams** are groups of users used for access control and policy scoping across the platform. Granting a team access to a resource automatically grants access to all its members.

Note: There is an implicit `everyone` team which includes all users in the tenant (but not virtual accounts).

## Creating Teams (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `team`.

### Phase 2: Validate and Apply

1. Collect the team name and member emails from the user.
2. Build the manifest following the JSON schema strictly.
3. Call `apply_manifest` with `dryRun: true` to validate.
4. If validation fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` without dry-run to create the team.

### Manifest Structure

```yaml
type: team
name: <unique-team-name>
members:
  - <user-email-1>
  - <user-email-2>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I validate with `apply_manifest` (dryRun: true) before creating?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about teams.
Search terms: "team management", "create team", "team access control", "SSO group sync"
