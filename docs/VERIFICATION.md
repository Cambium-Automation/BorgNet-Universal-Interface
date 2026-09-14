# Verification

Initial release verification:

- 16 passing Python tests using isolated temporary state.
- All four provider protocol adapters exercised with synthetic HTTP fixtures.
- Parallel dispatch, partial failure, synthesis thresholds, follow-up history, selected-context isolation, model discovery, and an explicit model-pull request checked.
- Actual local MCP sessions over stdio and Streamable HTTP, including tool discovery, resource discovery, text reads, and exclusion of unshared context.
- Origin/Host/write-token checks, saved-key redaction, owner-only secret-file permissions, SSH argument validation, and empty first-launch state checked.
- Browser JavaScript syntax and executable keyboard-handler tests passed.
- Browser walkthrough: create a synthetic connection, discover and select its model, send with Enter, receive the fixture response, and preserve a two-line draft with Shift+Enter.
- Standalone arm64 macOS native shell compiled with a macOS 26 SDK; ad-hoc signature verification passed; native window inspected. Visible title bar, flush content corners, translucent surfaces, compact 8 px boxes, and 6–7 px controls are retained.
- Package wheel built and installed into an isolated environment; browser assets included in the package.
- Public source scan excludes private machine inventory, credentials, local data, generated app bundles, and development paths. Repository history begins with this standalone implementation.

Evidence limits: no real cloud credentials, real model downloads, live remote SSH authentication, or private infrastructure were used. Synthetic HTTP fixtures verify request/response contracts; they do not certify every provider or model. Windows/Linux browser installation and older macOS rendering were not manually exercised. The CI matrix adds Python-version coverage after publication. Dependency deprecation warnings do not represent failed tests.

## Collaborative decisions and native icon

37 automated tests pass, including question/implementation selection, malformed/self/duplicate/missing ballots, partial participation, quorum refusal, and final-editor fallback. These are controlled fixtures, not a benchmark of model answer quality. The native icon is generated from `native/render-icon.swift`, packaged as a multi-resolution ICNS, and the app bundle is ad-hoc signed and verified.

A controlled three-model browser walkthrough confirmed Enter dispatch, collapsed proposal/review cards, the expanded final decision, smoke-tinted sent messages, and the untinted final answer. The API integration check also confirms the default collaborative path persists its selection to history.

The 50-connection capacity test creates 50 entries, edits at capacity, rejects entry 51 without saving its secret, dispatches all 50 through proposals and peer review (49 valid peer scores per model), and verifies the final decision and persisted history. This uses synthetic providers, not 50 physical GPUs.

The aggregated participant bar was checked with staggered synthetic responses: pending Thinking labels, expandable in-progress proposals, completed green names, peer review transitions, and a separate final answer.

Model inventory persistence is verified across server recreation, with invalidation on endpoint changes and deletion. Provider redirect tests confirm credentials are not forwarded; the model-options JavaScript check covers stale Ollama thinking settings. See [security review](SECURITY-REVIEW.md) for the release review scope.

Per-model generation profiles preserve CPU/GPU settings across model switches. Regression checks verify that `num_gpu: 0` reaches Ollama without permitting overrides of protocol fields, that profiles survive configuration persistence, and that new models do not inherit a previous model's GPU-layer override.

Peer reviews receive only other participants' proposals, an explicit list of required IDs, and an Ollama JSON schema for the ballot. Local validation still rejects missing, duplicate, or self-votes. Format retries include the prior malformed answer for correction. Proposal prompts include the configured model identity.

Provider expansion: 44 Python tests pass, plus keyboard/model-options JavaScript checks. New controlled HTTP fixtures exercise Responses and Cohere authentication, history, output parsing, incomplete responses, Cohere model pagination, and Anthropic/Gemini options. See [provider setup and scope](PROVIDERS.md). Cloud accounts were not used for these checks.
