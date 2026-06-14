---
name: personal-access-tokens
description: Create and manage Personal Access Tokens (PATs) for user authentication against the Gateway and platform APIs.
---

**Personal Access Tokens (PATs)** are tied to a user and used for development and testing. For production use, recommend Virtual Account Tokens (VATs) instead.

## Creating Personal Access Tokens (Write Flow)

### Phase 1: Create PAT

1. Call `create_personal_access_token` with the required input format for the tool.

Note: PAT creation does not use the manifest/apply workflow — it uses a dedicated tool.

### Checklist

- [ ] Did I call `create_personal_access_token` with the correct input format?

## Searching Docs for Additional Information

Use `search_docs` to search for additional information about authentication tokens.
Search terms: "personal access token", "PAT creation", "authentication", "API key management"
