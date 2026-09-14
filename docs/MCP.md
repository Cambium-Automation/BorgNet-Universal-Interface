# Shared MCP setup

BorgNet is both an MCP client and an optional read-only MCP server. It uses the official Python MCP SDK for protocol negotiation and transport handling.

## Bring a data source into BorgNet

1. Open **Shared context → Connect MCP**.
2. For Streamable HTTP, supply the server's MCP URL and optional bearer token/environment variable. For stdio, supply an installed executable and a JSON argument array. The command runs under your user account; configure only servers you trust.
3. Choose **Inspect & fetch**. Select a resource, or review a tool and enter its arguments as a JSON object.
4. Fetch. A tool call can perform actions defined by its server. The returned text is stored privately in your context library.
5. Check the item to send it with the next prompt to the selected models. Attaching context to a cloud provider transmits that text to the provider.

The current client supports bearer-token HTTP auth and explicitly configured environment variables, not interactive OAuth. Legacy HTTP+SSE transport and binary context forwarding are not supported. MCP discovery paginates up to 20 pages; resource templates are not currently shown. Text fetches are capped at 100,000 characters, and attached context is capped at 150,000 characters per request.

## Let another application read shared context

Enable **Share this text via BorgNet's MCP server** on selected items. In a desktop MCP client, use a configuration of this shape, replacing paths with your installation:

```json
{
  "mcpServers": {
    "borgnet": {
      "command": "/absolute/path/to/.venv/bin/borgnet",
      "args": ["--data-dir", "/absolute/path/to/your/workspace", "mcp"]
    }
  }
}
```

The stdio server exposes:

- `list_shared_context`: IDs and titles of explicitly shared entries.
- `read_shared_context(context_id)`: the text of one shared entry.
- `borgnet://shared/context`: a resource containing the shared index.

No model calls, remote commands, credentials, endpoint inventories, or conversation history are exposed. Unsharing an item makes it unavailable to future reads, but cannot retract a copy that another client has already fetched.

## Read from another computer over SSH

Use a trusted SSH connection as the stdio transport. On the client computer, configure an installed `ssh` executable with arguments equivalent to:

```json
{
  "mcpServers": {
    "borgnet-remote": {
      "command": "ssh",
      "args": [
        "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "operator@workspace.example.com",
        "/absolute/path/to/.venv/bin/borgnet", "mcp"
      ]
    }
  }
}
```

Replace the example host, user, and executable path. The remote command defaults to that account's `~/.borgnet`; for a different data directory, configure `BORGNET_DATA_DIR` in a trusted remote wrapper. SSH protects transport and provides authentication; no public MCP listener is started. Only grant remote shell access to trusted users. This is transport configuration, not per-item multi-user access control.

Protocol reference: [official Python SDK](https://github.com/modelcontextprotocol/python-sdk), [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
