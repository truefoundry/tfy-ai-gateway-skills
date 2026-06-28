---
name: personal-access-tokens
description: Create and manage Personal Access Tokens (PATs) for user authentication against the Gateway and platform APIs.
---

**Personal Access Tokens (PATs)** are tied to a user and used for development and testing. They become invalid when the user leaves the organization. For production use, recommend Virtual Account Tokens (VATs) instead.

> **Note**: Each PAT must be assigned to a **team**. The team **cannot** be `everyone` — you must use a specific named team. If the user is not part of any team, ask them to contact their admin to be added to one.

## Creating Personal Access Tokens (Write Flow)

### Phase 1: Gather Requirements

1. Ask the user what the PAT is for (development, testing, CI, etc.).
2. Ask the user which **team** to assign the PAT to. Explain that `everyone` is not allowed — they must specify or create a named team.
3. Call `get_me` to get the current user's identity.

### Phase 2: Create PAT

1. Call `create_personal_access_token` with the required input format for the tool. Include the team assignment.

> **CRITICAL**: Do NOT use `apply_manifest` or `get_manifest_json_schema` for PATs. PATs have no manifest. Use the `create_personal_access_token` tool directly.

### Checklist

- [ ] Did I recommend Virtual Accounts (VATs) for production use cases?
- [ ] Did I ask the user which team to assign the PAT to?
- [ ] Did I confirm the team is NOT `everyone`?
- [ ] Did I call `get_me` to resolve the current user?
- [ ] Did I call `create_personal_access_token` with the correct input format?

For more info: `search_docs` with "personal access token", "PAT creation", "API authentication".
