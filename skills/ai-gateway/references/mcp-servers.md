---
name: mcp-servers
description: Deploy and connect MCP Servers to the AI Gateway to provide tools to models and agents
---

**MCP Servers** can be registered to MCP Gateway. MCP Servers can be of type `mcp-server/remote` or `mcp-server/openapi`.
**Virtual MCP Servers** allows to compose tools from multiple MCP Servers into a single MCP Server.

## Fetching existing MCP servers

Use the `gateway_list_mcp_servers` tool to get the list of all MCP servers. The response would look like this:

```yaml
data:
  - id: ...
    manifest:
      name:  mcp-server-1
      type: mcp-server/remote
      # Fields specific to mcp-server/remote
    - id: ...
      manifest:
        name:  mcp-server-2
        type: mcp-server/virtual
        servers:
          - name: mcp-server-1
            enabled_tools:
              - tool-1
              - tool-2
          - name: mcp-server-2
            enabled_tools:
              - tool-3
              - tool-4
        # Fields specific to mcp-server/virtual
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

## Searching Docs for Additional Information

The content above covers common operations. For conceptual questions, setup guides, or anything not fully answered above, search the docs.

Use `search_true_foundry_docs` to search for additional information about mcp servers.
Search terms: "mcp gateway", "mcp oauth", "mcp server registry", "openapi to mcp server", "virtual mcp servers"

