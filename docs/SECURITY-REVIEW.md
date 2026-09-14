# Release security review — 2026-09-13

Scope: the Python server, provider/SSH adapters, explicit MCP integration, browser rendering, native shell, installed dependencies, and tracked Git history. This is a focused code and configuration review with regression checks, not a penetration test or a guarantee of security.

## Findings and checks

- The server binds to loopback. Host/Origin checks and a per-process write token reject foreign requests. Existing regression checks pass.
- Provider credentials stay in headers and owner-only local files; state responses omit key values. Provider redirects are refused, including a regression test proving a credentialed request is not forwarded to a redirect target. Upstream error bodies are not reflected to the UI.
- SSH uses argument arrays, strict host-key verification, key/agent authentication, and loopback-only forwarded ports. No model-generated shell execution is provided.
- Model responses and endpoint labels render as text nodes. The native shell restricts navigation to loopback HTTP(S), and the web server supplies a restrictive Content Security Policy.
- MCP sharing exposes only explicitly shared text. Private context, endpoint configuration, conversations, and credentials are excluded. MCP calls and installed stdio commands are explicitly user-configured; their capabilities depend on those external servers.
- Saved discovery results remain outside the repository with owner-only permissions, are removed when a connection is deleted, and are invalidated when its endpoint changes. Switching Ollama models drops the previous model's thinking override.
- `pip-audit` found no known vulnerabilities in the 31 audited third-party runtime packages. The local first-party distribution was skipped by the advisory lookup because it is installed from a file URL; its source is covered by this code review. Results are a point-in-time check of the installed environment, not every dependency version permitted by the package ranges.
- Scanned 55 historical Git blobs plus the working tree for private machine identifiers, private-key markers, token patterns, and exact locally configured secret values: no matches. No private configuration or model inventory is included in this report.
- 33 Python tests pass, along with JavaScript syntax, Enter/Shift+Enter behavior, and model-option switching checks.

## Operating boundary

BorgNet is for a trusted single-user machine, not a public multi-user service. Do not expose its loopback server through a public proxy. Model/provider availability, remote runtime security, generated-answer correctness, and third-party MCP tool behavior are outside this review. Private runtime configuration remains local; the public repository starts empty.
