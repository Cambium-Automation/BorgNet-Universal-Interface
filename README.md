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

Open the **private launch link printed by `borgnet serve`**. It unlocks http://127.0.0.1:7337 for this browser tab. Click **Connect**, choose a protocol, enter your endpoint and credentials if needed, then save. Model discovery runs against that endpoint. Choose a model, enter your prompt, and press **Enter**. **Shift+Enter** inserts a new line; IME composition is preserved.

This is a local application. Its web server binds only to loopback. Keep it running while using the browser or native shell.

## Debian installer

A Debian-family desktop package and build instructions are available in [packaging/debian](packaging/debian/README.md). Install the `.deb` with `sudo apt install ./borgnet_0.1.0-1_all.deb`, then run `borgnet` or use the application menu. First launch requires Internet access to set up Python dependencies. The Linux package uses the browser interface; native Apple desktop blur is macOS-only.

## Connections

| Adapter | API base URL convention | Discovery | Chat | Model downloads |
| --- | --- | --- | --- | --- |
| Ollama | `http://localhost:11434` | `/api/tags` | `/api/chat` | Explicit `/api/pull` |
| OpenAI-compatible | Provider base ending in `/v1`, when required | `/models` | `/chat/completions` | Managed by provider |
| Anthropic | `https://api.anthropic.com/v1` | `/models` | `/messages` | Managed by provider |
| Gemini | `https://generativelanguage.googleapis.com/v1beta` | `/models`, filters generation-capable models | `generateContent` | Managed by provider |

Compatible local servers include those exposing OpenAI-style chat completions. Compatibility depends on the endpoint and chosen model, not its brand. You may enter an explicit model ID when a provider disables discovery. There is no bundled model list. Selecting an Ollama model loads it on the first inference request; the download button explicitly pulls a tag supplied by the user. The application does not install runtimes or manage remote system services.

Discovered model choices are saved in your private workspace and remain selectable after reload or restart. Use the refresh control to update them. Changing the endpoint clears its saved inventory. BorgNet remembers generation options per model when switching. For a model without saved options, Ollama thinking and GPU-layer overrides reset while general generation options remain. Set `num_gpu` to `0` for a runtime that needs CPU-only execution; hardware tuning stays in the private workspace.

Discovery currently reads the first model-list page for provider APIs. If a large account's desired model is not on that page, enter its model ID directly. Provider-specific extensions, Responses-only models, media generation, realtime audio/video, OAuth sign-in, and automatic agent tool execution are outside this initial release.

### Computers over SSH

In a connection, enable **Connect through SSH**, enter a hostname or SSH config alias, optional user, SSH port, and the remote API port. An optional SSH identity-file path and remote API bind address support services bound to a specific interface. BorgNet opens an SSH tunnel from an ephemeral local loopback port to the selected API bind address on that computer (loopback by default). The URL field supplies the API path prefix (for example `/v1`).

Cards and results show **SSH address + actual model ID**, or **API base URL + actual model ID** for direct connections. The purpose field is optional system guidance for that model; there are no predefined hardware roles.

SSH uses agent/key authentication (or the explicitly configured identity file), `BatchMode=yes`, `StrictHostKeyChecking=yes`, and no shell interpolation. First establish trusted access with your SSH client. BorgNet does not accept passwords, enroll host keys, install a remote runtime, execute model-generated commands, or weaken SSH configuration. Remote unencrypted HTTP endpoints must be reached through SSH; direct remote APIs require HTTPS.

### API keys

Use a key in the connection form, or enter the name of an environment variable available to the BorgNet process. Environment variables take precedence. Saved secrets are separate from configuration, written with owner-only file permissions, and never returned by the API. They are **not encrypted at rest**; use environment variables if that is preferable. Leave the key field blank when editing to keep the saved key. Remove a connection to delete its saved key.

### Per-connection runtime options

The connection form includes a JSON options object and a response timeout. Ollama accepts `num_ctx`, `num_predict`, `num_gpu`, `temperature`, `top_p`, `top_k`, `think`, and `keep_alive`. OpenAI-compatible endpoints accept `max_tokens`, `max_completion_tokens`, `temperature`, `top_p`, `top_k`, `reasoning_effort`, `reasoning_format`, and `thinking_budget_tokens` when their provider supports them. Model IDs, messages, and streaming controls cannot be overridden through this object. Other adapters retain their protocol defaults. The chosen synthesis connection is saved with workspace settings.

## One prompt, several perspectives

A workspace supports **up to 50 model connections**, and all 50 can participate in one prompt. A connection is a configured endpoint/model entry, not a GPU: one computer can supply several entries, and one runtime may use several GPUs.

Enable the connections you want to use. Enter sends to every enabled connection with a selected model. With two or more models, collaboration is the default: independent proposals, peer scoring of every other proposal, then a final decision from the three highest-ranked proposals. Questions select one supported answer; code/design requests select up to three complementary proposals and include implementation and verification plans. The selected collaboration model writes the final decision, with one fallback editor if it fails. One expandable conference bar shows every participant: white with “Thinking” during each active round, green after a completed response, and an explicit error state for failures. Open it at any time to read proposals and peer reviews as they arrive. The unified answer appears below the bar after the decision completes. Your sent messages have a translucent smoke background; the unified response stays clear.

A reviewer receives only its peers’ proposals, with exact required IDs and an Ollama JSON-schema request where supported. A valid review must score every peer exactly once and cannot score itself. Validation remains mandatory even when a provider supports structured output. A decision needs at least two successful proposals and valid reviews from at least half the responders (minimum two). Invalid reviews get one format retry, then abstain. Missing participation is disclosed. Scores guide model judgment; they do not prove correctness. At 50 participants, a successful round makes 50 proposal calls, 50 review calls, and one final decision call before any retries. Each reviewer scores 49 peers, so configure sufficient output tokens and context capacity on the chosen runtimes. The 50-participant path is tested with synthetic providers, not a physical 50-GPU cluster. BorgNet selects and plans work, but does not execute generated code or edits. Choose “Independent answers only” to skip review.

Collaboration allows 12,000 prompt characters, excerpts shared reference data to 24,000 characters and the proposal pool to approximately 18,000 characters, and bounds each provider call by its configured timeout or 600 seconds, whichever is shorter. Public text streams as it arrives during proposals, peer reviews and the final decision. The conference opens automatically, and completed reviews replace their provisional JSON with validated summaries. Grok and Copilot CLIs and supported HTTP APIs stream live; Codex/Gemini CLI adapters currently return completed messages and are labeled accordingly. Reasoning and tool events are not displayed. Errors are retained in history. Stopping cancels local pending calls; providers may continue already accepted work.

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

BorgNet is designed for a trusted single-user computer, not as an Internet-facing multi-user service. It rejects foreign Host/Origin requests and requires a private per-process browser credential for all API reads and writes, plus a separate request token for writes. The launch credential is stored in an owner-only file and passed through a URL fragment, then removed from the address bar; it is never sent in cookies. Media uses a separate read-only credential. It intentionally permits user-configured local endpoints and installed MCP commands. Do not expose the server through a public reverse proxy.

## Development and verification

```sh
python -m pip install -e '.[test]'
pytest -q
node --check borgnet/web/app.js
node tests/keyboard.cjs
```

Tests use synthetic HTTP provider fixtures and a real local MCP stdio session. They cover all four protocol adapters, discovery, downloads, parallel dispatch, peer ballot validation, ranking, implementation plans, incomplete participation, editor fallback, synthesis, history, privacy boundaries, SSH argument validation, and Enter behavior. They do not use real credentials, download real models, or contact any user's computers. See [verification notes](docs/VERIFICATION.md) for the tested scope and [architecture](docs/ARCHITECTURE.md) for extension points.

See [provider setup](docs/PROVIDERS.md) for local/cloud presets, six supported text protocols, generation options, and compatibility limits.

### Image generation and library

The Image generation tab supports OpenAI, Gemini, and xAI image APIs. Configure a provider in the tab, set its `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `XAI_API_KEY` environment variable, or reuse a chat connection whose URL exactly matches the provider's official API base URL. Model discovery runs when you open the image tab. Catalog entries without credentials remain unavailable; discovery does not guarantee quota or model access.

For native image tools through an already authenticated CLI, install `codex` or `grok` on your PATH and enable its CLI connection in BorgNet. The connection toggle also controls image availability. Alternatively set `BORGNET_CODEX_IMAGES=1` or `BORGNET_GROK_IMAGES=1` in the launch environment; a value of `0` explicitly disables that image adapter. These modes use the existing CLI sign-in without an additional image API key. CLI versions must support their native image tools; account usage limits still apply. Codex uses its CLI default model. No CLI connection is enabled or contacted by default.

Generated images remain in your local state directory. Each gallery item and enlarged image has **Save to Downloads** and **Delete** controls. Saving exports the original PNG, JPEG, or WebP on the computer running BorgNet with a collision-safe filename. Deletion removes the image from the active gallery and retains it under **Recently deleted**, with **Restore** available; it does not erase image bytes or export copies. Provider rejections and quota errors are displayed separately.

Native generation runs in a separate job directory with a bounded timeout. Public assistant failure messages may be shown; private reasoning and raw tool transcripts are not displayed. Job logs remain local. This release does not include machine-specific image runtimes or private security specialist interfaces.


### Video generation

The **Video generation** tab supports text-to-video through xAI Grok Imagine,
Google Veo 3.1 and OpenAI Sora 2 APIs. It reuses the matching official-provider
chat/image API key or `XAI_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_API_KEY`.
**Connect provider API** opens the shared credential form. CLI subscription
sign-in does not provide video API credentials. Keys being present does not
prove model access or quota; video is billed by the provider.

Choose a model, duration and format, then generate. This initial implementation
uses 720p and accepts one pending job at a time. Job IDs persist in private
`video-jobs.json`; reloading resumes polling without creating another video.
Keep the page open to poll and download completed clips promptly: provider
URLs expire. Closing the page does not cancel generation or provider charges.
An interrupted submission is marked uncertain rather than automatically retried;
check provider history before submitting again. Completed MP4s (up to 256 MB)
are stored privately in `api-videos`, with inline playback and Download MP4.
This release supports text prompts; image references, editing and extensions
are not yet wired in. No video model weights or extra SDKs are installed.

Adapters follow the official [xAI video API](https://docs.x.ai/developers/model-capabilities/video/generation),
[Google Veo API](https://ai.google.dev/gemini-api/docs/veo), and
[OpenAI video API](https://developers.openai.com/api/reference/resources/videos).
Tests cover synthetic provider submission, completion, persistence, download,
credential isolation and failure. Live video generation still requires an
account with video API access.


### Security review

See [SECURITY.md](SECURITY.md) for the threat model, hardening, validation and
remaining boundaries. Use the private launch link after server restarts; the
native macOS app and Debian launcher read it automatically on launch. Do not
share launch links, browser session storage, or `browser-session.json`.


For checkout-based MCP clients, `scripts/shared_context_mcp.py --data-dir PATH mcp`
provides the same read-only shared-context server without relying on an editable
Python installation. Launch it with the checkout virtualenv Python. Configure it
as a stdio MCP source; it starts on demand, so no additional network port is opened.
Only entries marked **Share via MCP** are listed/read. An empty shared index is expected
until you explicitly share an item.
