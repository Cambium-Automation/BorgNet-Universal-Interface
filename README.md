# BorgNet Universal Interface

A local-first glass workspace for the models and computers **you** choose.

Bring local runtimes, remote computers, cloud APIs, and MCP data sources into one interface. Start with an empty workspace, discover models from your endpoints, assign each connection a purpose, and send one prompt to one or several models. With multiple models selected, they propose solutions, independently review their peers, and produce one ranked final answer or implementation plan.

No bundled accounts, machine inventory, preselected models, credentials, private workflows, or conversation data. No telemetry, external fonts, hosted frontend, or automatic network discovery.

## Start

Requires **Python 3.11+**. macOS, Linux, and Windows can use the browser workspace; SSH connections require an installed OpenSSH client.

```sh
git clone https://github.com/Cambium-Automation/BorgNet-Universal-Interface.git
cd BorgNet-Universal-Interface
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
borgnet serve
```

On Windows, activate with `.venv\Scripts\Activate.ps1` and use `python` if `python3` is unavailable.

Open **http://127.0.0.1:7337**. Click **Connect**, choose a protocol, enter your endpoint and credentials if needed, then save. Model discovery runs against that endpoint. Choose a model, enter your prompt, and press **Enter**. **Shift+Enter** inserts a new line; IME composition is preserved.

This is a local application. Its web server binds only to loopback. Keep it running while using the browser or native shell.

## Connections

| Adapter | API base URL convention | Discovery | Chat | Model downloads |
| --- | --- | --- | --- | --- |
| Ollama | `http://localhost:11434` | `/api/tags` | `/api/chat` | Explicit `/api/pull` |
| OpenAI-compatible | Provider base ending in `/v1`, when required | `/models` | `/chat/completions` | Managed by provider |
| Anthropic | `https://api.anthropic.com/v1` | `/models` | `/messages` | Managed by provider |
| Gemini | `https://generativelanguage.googleapis.com/v1beta` | `/models`, filters generation-capable models | `generateContent` | Managed by provider |

Compatible local servers include those exposing OpenAI-style chat completions. Compatibility depends on the endpoint and chosen model, not its brand. You may enter an explicit model ID when a provider disables discovery. There is no bundled model list. Selecting an Ollama model loads it on the first inference request; the download button explicitly pulls a tag supplied by the user. The application does not install runtimes or manage remote system services.

Discovery currently reads the first model-list page for provider APIs. If a large account's desired model is not on that page, enter its model ID directly. Provider-specific extensions, Responses-only models, media generation, realtime audio/video, OAuth sign-in, and automatic agent tool execution are outside this initial release.

### Computers over SSH

In a connection, enable **Connect through SSH**, enter a hostname or SSH config alias, optional user, SSH port, and the remote API port. An optional SSH identity-file path and remote API bind address support services bound to a specific interface. BorgNet opens an SSH tunnel from an ephemeral local loopback port to the selected API bind address on that computer (loopback by default). The URL field supplies the API path prefix (for example `/v1`).

Cards and results show **SSH address + actual model ID**, or **API base URL + actual model ID** for direct connections. The purpose field is optional system guidance for that model; there are no predefined hardware roles.

SSH uses agent/key authentication (or the explicitly configured identity file), `BatchMode=yes`, `StrictHostKeyChecking=yes`, and no shell interpolation. First establish trusted access with your SSH client. BorgNet does not accept passwords, enroll host keys, install a remote runtime, execute model-generated commands, or weaken SSH configuration. Remote unencrypted HTTP endpoints must be reached through SSH; direct remote APIs require HTTPS.

### API keys

Use a key in the connection form, or enter the name of an environment variable available to the BorgNet process. Environment variables take precedence. Saved secrets are separate from configuration, written with owner-only file permissions, and never returned by the API. They are **not encrypted at rest**; use environment variables if that is preferable. Leave the key field blank when editing to keep the saved key. Remove a connection to delete its saved key.

### Per-connection runtime options

The connection form includes a JSON options object and a response timeout. Ollama accepts `num_ctx`, `num_predict`, `temperature`, `top_p`, `top_k`, `think`, and `keep_alive`. OpenAI-compatible endpoints accept `max_tokens`, `max_completion_tokens`, `temperature`, `top_p`, `top_k`, `reasoning_effort`, `reasoning_format`, and `thinking_budget_tokens` when their provider supports them. Model IDs, messages, and streaming controls cannot be overridden through this object. Other adapters retain their protocol defaults. The chosen synthesis connection is saved with workspace settings.

## One prompt, several perspectives

Enable the connections you want to use. Enter sends to every enabled connection with a selected model. With two or more models, collaboration is the default: independent proposals, peer scoring of every other proposal, then a final decision from the three highest-ranked proposals. Questions select one supported answer; code/design requests select up to three complementary proposals and include implementation and verification plans. The selected collaboration model writes the final decision, with one fallback editor if it fails. Proposals and reviews stay available in expandable cards. Your sent messages have a translucent smoke background; the unified response stays clear.

A valid review must score every peer exactly once and cannot score itself. A decision needs at least two successful proposals and valid reviews from at least half the responders (minimum two). Invalid reviews get one format retry, then abstain. Missing participation is disclosed. Scores guide model judgment; they do not prove correctness. BorgNet selects and plans work, but does not execute generated code or edits. Choose “Independent answers only” to skip review.

Collaboration allows 12,000 prompt characters, excerpts shared reference data to 24,000 characters and the proposal pool to approximately 18,000 characters, and bounds each provider call by its configured timeout or 600 seconds, whichever is shorter. Completion events stream after full responses, not token by token. Errors are retained in history. Stopping cancels local pending calls; providers may continue already accepted work.

Follow-up prompts include up to eight prior turns for the same connection in the current conversation. **New conversation** starts fresh; **History** resumes a saved conversation. Selected context is attached only when you choose it. Context and prompts are transmitted to the selected providers, including cloud providers. **Stop** cancels local pending requests; a remote provider may continue work or charge for a request it has already accepted.

## Shared MCP context

Connect MCP servers using **Streamable HTTP** or an installed **stdio** command. Inspect available tools and resources, review a tool's description and JSON input schema, and explicitly fetch a result. The textual result becomes a private context item. Check it to attach it to your next prompt for all selected models.

You can also make BorgNet an MCP source for another application. Mark individual items **Share via MCP** and configure that application to launch `borgnet mcp`. Only those items are readable. Credentials, connections, and conversations are never exposed by this MCP server. Nothing is shared by default.

See [MCP setup](docs/MCP.md) for client configuration and access from another computer. MCP tools may have side effects; the interface executes only the tool and arguments you explicitly submit. There is no autonomous tool loop.

## Native macOS glass shell

Build with an Xcode command-line toolchain containing the macOS 26 SDK:

```sh
bash native/build.sh
```

Start `borgnet serve`, then open `dist/BorgNet Universal Interface.app`. The shell uses native Liquid Glass on macOS 26+, with a visual-effect fallback on older systems. Its title bar remains visible, and the glass content meets it flush. The web interface supports system, light, and dark themes. The surrounding native title bar follows macOS appearance. While the window is active, an 8% frost blend and a 2% dark backing improve text contrast without fading the content. These extra layers fade out when inactive, leaving the system glass treatment visible.

The build is ad-hoc signed for local use. It does not install or replace other apps, require an existing app as a template, or contain a developer's absolute paths. Distribution with Apple notarization requires the distributor's own signing identity. Older-system rendering and Intel builds have not been verified.

Advanced: the shell reads `BORGNET_URL` (default `http://127.0.0.1:7337/?native=1`) and `BORGNET_MATERIAL=visual-effect` from its launch environment. Navigation is restricted to loopback. It does not start or stop the Python server.

## User data and boundaries

Configuration, secrets, context, and the most recent 100 request records live in `~/.borgnet`, outside the checkout. Override with `BORGNET_DATA_DIR` or the global `--data-dir` flag:

```sh
borgnet --data-dir /path/to/your/workspace serve --port 7337
```

Use one BorgNet server process per data directory. JSON writes are atomic; concurrent processes writing the same directory are not supported. Back up or delete that directory using your normal file tools. Do not commit it or publish exported user data. Secrets, state, build outputs, and environment files are ignored by Git.

BorgNet is designed for a trusted single-user computer, not as an Internet-facing multi-user service. It rejects foreign Host/Origin requests and requires a per-process request token for writes. It intentionally permits user-configured local endpoints and installed MCP commands. Do not expose the server through a public reverse proxy.

## Development and verification

```sh
python -m pip install -e '.[test]'
pytest -q
node --check borgnet/web/app.js
node tests/keyboard.cjs
```

Tests use synthetic HTTP provider fixtures and a real local MCP stdio session. They cover all four protocol adapters, discovery, downloads, parallel dispatch, peer ballot validation, ranking, implementation plans, incomplete participation, editor fallback, synthesis, history, privacy boundaries, SSH argument validation, and Enter behavior. They do not use real credentials, download real models, or contact any user's computers. See [verification notes](docs/VERIFICATION.md) for the tested scope and [architecture](docs/ARCHITECTURE.md) for extension points.
