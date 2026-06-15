---
name: mcp-servers
description: Deploy and connect MCP Servers to the AI Gateway to provide tools to models and agents
---

**MCP Servers** can be registered to MCP Gateway. MCP Servers can be of type `mcp-server/remote` or `mcp-server/openapi`.
**Virtual MCP Servers** allows to compose tools from multiple MCP Servers into a single MCP Server.

## Fetching existing MCP servers

Use the `list_mcp_servers_admin` tool to get the list of all MCP servers. The response would look like this:

```yaml
data:
  - id: ...
    fqn: truefoundry:mcp-server:mcp-server-1
    manifest:
      name: mcp-server-1
      type: mcp-server/remote
      # Fields specific to mcp-server/remote
    createdBySubject: { ... }
    createdAt: ...
    updatedAt: ...
  - id: ...
    fqn: truefoundry:mcp-server:mcp-server-2
    manifest:
      name: mcp-server-2
      type: mcp-server/virtual
      servers:
        - name: mcp-server-1
          enabled_tools:
            - tool-1
            - tool-2
        - name: mcp-server-3
          enabled_tools:
            - tool-3
            - tool-4
      # Fields specific to mcp-server/virtual
    createdBySubject: { ... }
    createdAt: ...
    updatedAt: ...
pagination:
  total: ...
  offset: 0
  limit: 100
```

## Generating Valid Manifests for MCP Servers

### Phase 1: Research MCP Server Schema

1. Use grep on `scripts/manifest_schemas.py` to understand schema of class `RemoteMCPServerManifest` / `OpenAPIMCPServerManifest` / `VirtualMCPServerManifest` and related classes.

    ```shell
    grep -A 20 -h -E 'class .+MCPServerManifest' scripts/manifest_schemas.py
    ```

Important: Ignore `MCPServerProviderAccount` and `MCPServerIntegration` classes. These are deprecated and should not be used.

### Phase 2: Generate Valid MCP Server Manifest

1. Using the discovered schema, write a YAML manifest to a file.
2. Use `python scripts/validate_schema.py --file-path <path-to-manifest>` to validate the manifest.
3. Repeat the process until the manifest is valid.

## Creating MCP Servers (Write Flow)

### Phase 1: Get Schema

1. Call `get_manifest_json_schema` with the MCP server type (e.g. `mcp-server/remote`, `mcp-server/openapi`, `mcp-server/virtual`) to get the full JSON schema.

### Phase 2: Determine Authentication

1. Use `ask_user_question` to ask the user what type of authentication they want (options depend on what the schema supports — typically: no auth, OAuth 2.0, API Key / Header-based).

2. **If OAuth 2.0 is selected**: You **MUST** call `get_mcp_server_oauth_config` with the MCP server's URL before proceeding. This returns the Raw OAuth 2.0 Authorization Server Metadata (RFC 8414) which provides `authorization_url`, `token_url`, supported `scopes`, and other metadata required to fill the auth config. Do NOT skip this step or guess the OAuth URLs.

3. Collect remaining auth details from the user (client_id, client_secret, scopes, etc.).

### Phase 3: Build and Validate

1. Build the manifest following the JSON schema strictly. Write it to a file.
2. Run `python scripts/validate_schema.py --file-path <manifest.yaml>` to validate. Fix and repeat until valid.
3. Call `apply_manifest` directly as a tool (NOT from code mode) with `dryRun: true`.
4. If dry-run fails, fix and retry.
5. Once dry-run passes, call `apply_manifest` directly as a tool (NOT from code mode) without dry-run to create the MCP server.

### Manifest Structure

```yaml
name: <unique-mcp-server-name>
description: <description>
url: <mcp-server-endpoint-url>
collaborators:
  - role_id: mcp-server-manager
    subject: user:<current-user-email>  # from get_me; ask user before adding others
type: mcp-server/remote
auth_data:
  type: oauth2
  grant_type: authorization_code
  authorization_url: <from-oauth-server-metadata>
  token_url: <from-oauth-server-metadata>
  client_id: <client-id>
  client_secret: <client-secret>
  jwt_source: access_token
  scopes:
    - <scope-1>
    - <scope-2>
```

### Checklist

- [ ] Did I call `get_manifest_json_schema` to get the current schema?
- [ ] Did I ask the user which auth type they want before proceeding?
- [ ] If OAuth, did I call `get_mcp_server_oauth_config` to get server metadata?
- [ ] Did I validate with `scripts/validate_schema.py` before dry-running?
- [ ] Did I dry-run with `apply_manifest` (dryRun: true) before creating?
- [ ] Did I apply without dry-run only after dry-run passed?

## Searching Docs for Additional Information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_docs` to search for additional information about mcp servers.
Search terms: "mcp gateway", "mcp oauth", "mcp server registry", "openapi to mcp server", "virtual mcp servers"
