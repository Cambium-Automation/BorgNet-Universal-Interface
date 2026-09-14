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
python -m pip --isolated install --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r requirements-bootstrap.txt
python -m pip --isolated install --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r requirements.txt
python -m pip --isolated install --no-deps --no-build-isolation .
borgnet adapters install
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

Most provider catalogs read the first model-list page; Cohere supports pagination. Enter a model ID directly if it is absent. Responses, image/video generation and opt-in CLI execution are supported by their respective adapters. Realtime audio/video sessions are not supported.

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

Collaboration allows 12,000 prompt characters, excerpts shared reference data to 24,000 characters and the proposal pool to approximately 18,000 characters, and bounds each provider call by its configured timeout or 600 seconds, whichever is shorter. Public text streams as it arrives during proposals, peer reviews and the final decision. The conference starts as a compact two-line auto-scrolling stream. Click it to expand the full output; scrolling back pauses auto-follow. Completed reviews replace their provisional JSON with validated summaries. Grok and Copilot CLIs and supported HTTP APIs stream live; Codex/Gemini CLI adapters currently return completed messages and are labeled accordingly. Reasoning and tool events are not displayed. Errors are retained in history. Stopping cancels local pending calls; providers may continue already accepted work.

Follow-up prompts include up to eight prior turns for the same connection in the current conversation. **New conversation** starts fresh; **History** resumes a saved conversation. Selected context is attached only when you choose it. Context and prompts are transmitted to the selected providers, including cloud providers. **Stop** cancels local pending requests; a remote provider may continue work or charge for a request it has already accepted.

## Shared MCP context

Connect MCP servers using **Streamable HTTP** or an installed **stdio** command. Inspect available tools and resources, review a tool's description and JSON input schema, and explicitly fetch a result. The textual result becomes a private context item. Check it to attach it to your next prompt for all selected models.

You can also make BorgNet an MCP source for another application. Mark individual items **Share via MCP** and configure that application to launch `borgnet mcp`. Only those items are readable. Credentials, connections, and conversations are never exposed by this MCP server. Nothing is shared by default.

See [MCP setup](docs/MCP.md) for client configuration and access from another computer. MCP tools may have side effects; the interface executes only the tool and arguments you explicitly submit. The shared-context panel has no autonomous tool loop. Installed text CLIs can use their own tools when explicitly enabled in Permissions.

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

### Model permissions

Use **Permissions** beside **Customize** to set shared defaults or overrides for each connection. The working folder is configurable and defaults to the BorgNet source directory. Settings apply to future text requests, including proposal, review and synthesis phases; they cannot be changed during an active text request. All tool grants default off.

Codex and Grok support web-only access with shell tools disabled. Full CLI access enables commands, file changes and network access without individual approvals for Codex, Grok and Copilot; the working folder is a starting directory, not a confinement boundary. Copilot requires full access for network tools. Gemini CLI, API and BitNet connections remain text-only. Browser clicking and desktop controls are available after `borgnet adapters install`, with separate opt-in toggles for Full CLI connections. Model API transport, media generation and explicit shared-context fetching are separate from these text-agent permissions. Installed CLI software and its local configuration remain trusted code.

### Debate and implementation

Choose **Method → Debate · argue & revise** in the composer. Each revision has one author followed by every participant's challenge, including a final self-check from the author. The next revision rotates authors and addresses the objections. Plain-language turns use a final revision-specific AGREE/DISAGREE line; missing or malformed assent does not count. Every selected model must explicitly accept the same candidate. The process stops at the selected revision limit (2–6 in the UI) or 15 minutes, retaining dissent instead of inventing consensus. Agreement is not proof of correctness.

Attached reference context and recent conversation answers are included with bounded excerpts. Discussion has tools disabled even if Full CLI access is configured. Enable **Implement after agreement** and choose an executor to let one supported CLI implement the accepted work under its existing Full CLI access grant. Only that executor receives tools, after consensus, and it must inspect the workspace, preserve existing changes and report verification. Implementation is not transactional: cancellation or failure can leave partial changes. Review the executor's evidence. No implementation occurs after dissent, a missing participant, or without the opt-in. This mode supports 2–8 models.

### Dependency maintenance

The recommended install and Debian launcher use exact package versions with SHA-256 hashes and accept wheels only. `requirements.txt` contains runtime dependencies; `requirements-bootstrap.txt` contains pip and setuptools; `requirements-dev.txt` adds tests and audit tools. Plain `pip install .` uses the supported version ranges and is not a reproducible locked install. No JavaScript packages are downloaded by the frontend.

CI verifies the lockfile install, Python tests, JavaScript checks, unused Python imports/undefined names, and advisory results. A weekly GitHub Actions audit and Dependabot updates are configured; they begin after these files reach the default branch with Actions enabled. Hashes verify package integrity against this lockfile, not that upstream code is harmless. Review updates and regenerate hashes before merging.

To refresh locks with an installed `uv`, run `uv pip compile pyproject.toml --universal --generate-hashes -o requirements.txt`, then compile `requirements-bootstrap.in` and `requirements-dev.in` the same way to their corresponding `.txt` files. Audit all resulting files and run the tests. Keep the OS, browser, CLI programs and MCP servers updated separately.

### Browser and computer-use adapters

`borgnet adapters install` downloads the Playwright Chromium revision and registers the gated Grok MCP connector when Grok is installed. `borgnet adapters status` reports binary availability and OS permissions without taking a screenshot or opening a page. Codex and Copilot receive MCP configuration for each request; Grok receives an expiring grant through its installed stdio connector. The registered connector exposes no control tools outside a granted BorgNet request.

In **Permissions**, choose shared defaults or a connection, enable **Full CLI access**, then enable **Browser control** and/or **Computer use**. Both adapter toggles default off. These controls provision the BorgNet adapters; Full CLI access itself remains broad enough to run other software. API/BitNet and Gemini adapters remain text-only. Debate discussion receives no automation grant; an authorized executor can use it after agreement.

The browser has a separate, temporary Chromium profile and supports navigation, accessibility snapshots, screenshots, labelled-field entry, clicks, keys and scrolling. It does not reuse personal cookies or allow file URLs, arbitrary JavaScript tools, uploads or downloads. Page contents can be sent to the selected provider. The desktop adapter observes and controls the current desktop using screenshots, clicks, printable text, basic keys and scrolling; screenshots may expose unrelated private information. It requires a new screenshot before each action, and uses a process lock to prevent competing model controllers.

macOS needs Accessibility and Screen Recording consent for the actual launching application/Python process. The adapter checks consent and does not change OS permissions. Linux desktop control requires an X11 session and an active display; Wayland and Windows desktop control are not supported in this version. Browser use requires a graphical session. **Permissions → Test browser** runs a fixed offline form test without granting a model access or changing permission settings. Browser/desktop actions can affect accounts and data, so grant access only for trusted tasks. OS protections and website confirmations are not bypassed.

The Debian package contains the adapter modules and hash-pinned Python dependencies plus native library requirements. Its first-launch setup downloads Chromium for the target machine; it is not an offline browser bundle. Re-run adapter installation after installing Grok later. Installed browser binaries are selected by the pinned Playwright revision; browser downloads use Playwright's official distribution endpoints, separate from the Python wheel hashes.

## Voice and video input

The Voice & video tab records microphone turns or camera clips and accepts existing audio/video files. Enable a Gemini API connection and select it as the input model. Dictation returns a transcript; voice conversation returns a short answer; video analysis answers your question about a clip. The camera preview is live, but model analysis is turn-based, not a continuous streaming call.

Recordings are capped at 60 seconds and 8 MB. Review the preview and select Send recording to upload to the selected provider. BorgNet does not persist these recordings or responses; provider retention and quotas still apply. Speak replies uses an available local system voice. Use latest response in Workspace moves text into an editable draft for any connected models. Microphone/camera access ends when leaving the tab or hiding the page. Native macOS capture requires the rebuilt app and OS permission; file input works without camera access.

## Scrolling image feed

In Image generation, select Grok through its existing sign-in or xAI API, enter a prompt, then choose Start scrolling feed. Feed controls are hidden for other providers. Scroll within the generated-image area to request another variation, or use Generate next variation. Each request uses the selected provider's account allowance or API billing. The default cap is eight requests, adjustable to 4, 8, 16 or 30. Pause stops subsequent requests; accepted requests may still complete. Changing settings invalidates the current feed, and leaving the tab or hiding the page pauses it. Provider errors pause the feed without automatic retries. Completed images remain in the normal image library; the active feed does not restart on reload.

## Community and free-tier providers

- **AI Horde images:** select Horde in Image generation. Anonymous access works without a key, but anonymous images are always shared for dataset use under Horde's rules. Volunteer workers can see prompts and results. Add an optional AI Horde account key through Connect image API to request unshared results. Active models are discovered live, and Auto lets Horde choose a worker. The adapter polls one job at a time, requests inline images, restricts execution to trusted workers, and attempts cancellation on timeout/failure. Queue priority and available workers determine speed.
- **Pollinations images:** add a Pollinations key through Connect image API (or set `POLLINATIONS_API_KEY`) and refresh models. The image catalog excludes models marked paid-only, but other models can still consume Pollen; set a budget on the provider's key. Text access is available under the Pollinations connection preset. No paid fallback is introduced.
- **OpenRouter text:** use the OpenRouter free-model preset and add a key or set `OPENROUTER_API_KEY`. The default `openrouter/free` model and `free_only` option restrict discovery and dispatch to free model IDs. Limits and availability are controlled by OpenRouter. Removing that option intentionally permits paid models.

These providers retain their own content policies. Image connections use the existing library and scrolling-feed controls. No keys are bundled with the application.

OpenRouter image generation is also available in Image generation. It reuses the saved OpenRouter connection key or accepts a separate key through Connect image API. Models come from OpenRouter's dedicated image catalog, including supported aspect ratios and quality settings; generation uses its `/images` endpoint. Image usage is billed separately from free text-model selection. The Grok scrolling feed stays exclusive to Grok.

Image and video history retains public provider replies, refusal messages, and outcome codes alongside successful media and failed attempts. Expand **Provider responses** in the library to read them. Credentials and URLs are redacted; private reasoning and raw payloads are excluded. Storage limits are reported when text is truncated. Clearing image history also deletes these reply records; replies discarded by older versions cannot be recovered.

Horde image requests wait up to 20 minutes for the queue. Temporary status/result network errors and HTTP 408/429/5xx gateway failures receive bounded backoff retries against the same job; submission is never automatically repeated. A temporary lack of suitable workers no longer cancels a queued request immediately. Terminal failures and the queue deadline still attempt cancellation.

## Optional local Bonsai images on Apple Silicon

The local adapter runs genuine ternary Bonsai Image 4B in a separate Python process using PrismML's MLX pipeline. It starts with 512×512 or similarly sized previews, four steps, a quantized text encoder, staged component eviction, and a 4 GB process RSS cutoff. These precautions reduce memory pressure; other applications still share the Mac's RAM.

Installation is opt-in and separate from BorgNet's web-service dependencies. Install the official `PrismML-Eng/mflux-prism` and `PrismML-Eng/image-studio` packages in an isolated environment, and download `prism-ml/bonsai-image-ternary-4B-mlx-2bit`. The adapter uses `scripts/bonsai_render.py` and an owner-local `local-image-runtime.json` configuration in BorgNet's data directory; no model weights are bundled in the application package.

The configured BitNet launcher must honor the same `model-switch.lock` across startup and inference. Bonsai acquires that gate, stops the managed BitNet process and waits for it to exit, renders offline, then exits its own process before releasing the gate. If stopping BitNet fails, Bonsai never loads. BorgNet automatically reloads the configured local BitNet endpoint on its next chat request. Other local models and manually launched server binaries are outside this gate.

For the standalone BitNet launcher used by this project, `scripts/bitnet-bonsai-memory-gate.patch` adds the shared gate to `runtime.py` startup and inference. Apply it in the BitNet installation directory before enabling local images; do not enable `ready` for an unguarded launcher. The configured `lock_path` must point to that installation's `model-switch.lock`. `python`, `runner`, `model_path`, `bitnet_python`, and `bitnet_runtime` must be absolute local paths. Use `variant: "ternary"` and set `ready: true` only after a test render succeeds. These executable paths are local installation configuration, not browser-editable connection settings.

Image generation has a persistent three-way source switch: Frontier, Open & community (OpenRouter, Horde, Pollinations), and Local. Each group remembers its selected model. OpenRouter can include proprietary models as well as open models. Switching groups does not submit a generation or erase history.
