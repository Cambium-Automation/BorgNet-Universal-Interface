# Architecture

The repository is standalone. The browser and macOS shell connect to a loopback FastAPI service. It reads user configuration from an external data directory and routes explicit requests through small protocol adapters.

- `borgnet/config.py`: validation, empty defaults, atomic local state and separate secret storage.
- `borgnet/providers.py`: discovery/chat adapters and owned SSH tunnel processes. No hardware inventory or static model registry.
- `borgnet/mcp_bridge.py`: official SDK client sessions plus the read-only, opt-in shared-context server.
- `borgnet/server.py`: same-origin API, parallel dispatch, per-provider errors, collaborative dispatch, optional independent synthesis, and local history.
- `borgnet/collaboration.py`: bounded proposal/review/decision rounds, validated peer ballots, deterministic ranking, quorum checks, and an auditable final selection.
- `borgnet/web/`: dependency-free browser UI, glass styling, dynamic cards, accessible forms, and safe text rendering. Model text is rendered as text, not trusted HTML.
- `native/`: independent AppKit/WKWebView shell, public glass APIs, normal title bar, and no dependency on another installed bundle.

## Adding another protocol

Add a protocol value to `Connection.kind`, implement model discovery and chat mapping in `Providers`, add a form option, and supply mocked request/response tests. Keep the provider's key in request headers. Do not put credentials into URLs, return them to the browser, or include upstream error bodies in user-visible errors. Treat an empty public answer as a failed response.

A connection is identified by an opaque generated ID. Its display address comes from its endpoint or SSH settings, and its model ID is discovered or entered by the user. The optional purpose is sent as that provider's system guidance. No connection receives privileges from its label or model name.

## Boundaries

There is no automatic execution of model-generated commands, remote machine provisioning, training pipeline, robot interface, private routing logic, or agent delegation engine. Explicit MCP calls may have the capabilities of their configured server. Endpoint discovery and Ollama pulls happen only in response to UI actions.

The application sends provider responses as NDJSON events after each full response completes. It supports cancellation of local pending requests, but does not claim to stop work already accepted by an external provider. History and context are bounded. A single server process owns writes to each data directory; the MCP sharing process only reads atomically replaced files.
