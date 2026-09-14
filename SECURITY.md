# Security boundaries and review

Reviewed 2026-09-14. BorgNet is a **single-user, loopback-only application**, not a shared web service. This review and its regression tests reduce known risks; they are not a guarantee against every attack or an independent penetration test.

## Hardening from this review

- **High: local unauthenticated API access.** Previously another OS user/process could obtain the write token and configure executable MCP commands through the API. All API access now requires a random per-launch credential stored in owner-only workspace state. The launcher passes it in a URL fragment; JavaScript removes the fragment and keeps the credential in per-origin session storage. API requests use a header, not a cross-port cookie. Native and Debian launchers load the credential automatically. Server restart rotates it. Writes additionally require the existing CSRF token.
- **Medium: credential reuse after destination edits.** A changed provider/MCP destination could retain a saved key or environment reference. Such changes are now rejected unless an explicit replacement key is supplied and the inherited environment-key reference removed. Creating a new connection is the preferred way to change destinations.
- **Medium: unbounded memory/disk consumption.** Request limits now count actual streamed bytes (including chunked requests) instead of trusting Content-Length. Provider JSON replies are capped at 8 MB, image model catalogs at 2 MB, and image CLI output streams at 2 MB each. Image size is checked before reading. Existing image and video download limits remain.
- **Defense in depth:** foreign/same-site browser origins are rejected; malformed Host/length headers fail closed; same-origin resource policy blocks embedding private media; CSP disallows objects and framing. Media gets a separate credential accepted only for media reads, never command/configuration API access.
- **Credential transport:** HTTP MCP no longer follows redirects or inherits proxy configuration. Other provider HTTP clients already disable redirects and ambient proxies. Video downloads validate HTTPS/CDN hosts and keep API keys on the exact provider origin.
- **Local execution:** SSH uses argument arrays, strict host-key checking and no shell interpolation. Text CLI adapters disable tools by default. Permissions can explicitly enable web tools or full CLI execution; full access removes filesystem and network restrictions and allows commands without individual approvals across all conference phases. Do not enable it for untrusted prompts or context. Browser/desktop adapters are opt-in and use per-request grants; installing them alone does not enable them. Image adapters now remove Grok file-reading permission and disable Codex shell/plugins. Installed CLI and MCP software remains trusted code.
- **Workspace storage:** on POSIX, the state directory must belong to the current user and is tightened to mode 0700; state writes are atomic and mode 0600. Private session state and video artifacts are excluded from Git.
- **Native shell:** navigation and the blur bridge are restricted to the configured loopback origin, including scheme and port.
- **Dependencies:** pip-audit reported CVE-2026-13346 / GHSA-qwm4-qh6w-59xr in pip 26.1.2 (duplicated in the advisory feed). The local project installer was upgraded to a fixed version. Debian first-run setup upgrades pip to at least 26.2 and uses isolated configuration with the official PyPI index. A subsequent audit of the installed Python package inventory reported no known vulnerabilities.

## Validation

Regression tests cover unauthorized reads/writes, secret/media credential separation, cross-origin and malformed headers, chunked oversized bodies, old credentials after restart, endpoint credential transfer, provider reply bounds, media path validation, provider error handling and existing functionality. The running service was checked for HTTP 401 without a credential and HTTP 200 with its private credential. Native launch was checked after rebuilding/signing. The listener remains 127.0.0.1:7337; the local BitNet service also listens on loopback.

## Remaining trust and deployment limits

- Malware already running as the same OS user can read that user's credential files, browser storage and other application data. This is not a sandbox against a compromised account. Do not share private launch links.
- APIs and selected CLI providers receive submitted prompts/context. Only use provider endpoints and MCP programs you trust. MCP tools are explicitly invoked but may execute arbitrary actions with your account permissions. Prompt injection is not eliminated by a system prompt or by this review; do not treat model output as executable instructions.
- MCP transport parsing and installed third-party CLI software are outside the hard byte limits applied to the ordinary provider adapter. Only connect trusted MCP servers. No system-wide or npm/CLI dependency audit was performed.
- Secrets are protected by filesystem permissions, not encrypted at rest. Browser extensions with access to the workspace can read its content. Shared or publicly exposed hosting is unsupported, even with the launch credential. Do not proxy the app onto a LAN or the Internet.
- Debian packaging uses first-run online dependency installation. It is not a fully hash-locked/offline supply-chain bundle, and a real Debian installation still needs validation. Keep dependencies and the operating system current.
- This scan checks published Python advisories, not unknown vulnerabilities, upstream model providers, macOS/Linux security, or every possible abuse path. No live third-party attack testing was performed.

## Reporting

Do not post credentials or private launch links in GitHub issues. For a suspected vulnerability, use the repository's private vulnerability reporting mechanism if enabled; otherwise contact its maintainers privately before publishing exploit details.

Debate mode overrides CLI permissions to text-only during arguments and challenges. Only its explicitly selected executor receives the configured Full CLI access after unanimous revision-specific assent and an implementation opt-in. Peer agreement does not expand operator authorization, prove correctness, or sandbox the executor. Model instructions request scoped work and evidence; they cannot prevent every prompt-injection attack when full CLI execution is enabled.

## Dependency updates and reporting

Use the hash-pinned installation in README.md. Runtime, bootstrap and development locks are checked with `python scripts/audit_dependencies.py`; CI also checks inactive platform variants. A clean advisory result is time-limited and is not a guarantee against unknown flaws. The weekly audit and Dependabot configuration take effect once published with GitHub Actions enabled. See [the current review](docs/SECURITY-REVIEW.md) for findings, verification and limits.

Please avoid putting secrets or exploit details in public issues. Use GitHub private vulnerability reporting when available; otherwise request a private reporting channel from the maintainers without publishing the exploit or credentials.

Browser/computer adapters use stdio only, with owner-only expiring grant files and checks on every control tool. No unauthenticated remote-control port is added. Browser profiles are temporary and separate from personal profiles. Desktop access is current-user access, not an isolated machine, and is intentionally gated behind Full CLI permission. Shell privileges are not confined by these adapter toggles. macOS OS consent is required; Linux desktop support is X11 only. Model-provider accounts receive any observations included in tool results. Installation does not authorize transmitting arbitrary private data or performing unrelated actions.
