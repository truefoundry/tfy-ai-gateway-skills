---
name: teams
description: Create and manage teams — groups of users that can be used for access control, rate limiting, and budget scoping.
---

**Teams** are groups of users used for access control and config scoping across the platform. Granting a team access to a resource automatically grants access to all its members.

Note: There is an implicit `everyone` team which includes all users in the tenant (but not virtual accounts).

## Fetching existing teams

Use the `list_teams` tool to get the list of all teams. Use `get_team` to inspect a single team by name or ID.

## Creating Teams (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with type `team`.

### Phase 2: Build and Apply

Collect team name and member emails → build the manifest as JSON → pass to `validate_manifest` → fix if needed → pass to `apply_manifest`.

### Manifest Structure

```yaml
type: team
name: <unique-team-name>
members:
  - <user-email-1>
  - <user-email-2>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` with type `team`?

For more info: `search_docs` with "team management", "create team", "team access control".
