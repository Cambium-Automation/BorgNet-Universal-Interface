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

30 automated tests pass, including question/implementation selection, malformed/self/duplicate/missing ballots, partial participation, quorum refusal, and final-editor fallback. These are controlled fixtures, not a benchmark of model answer quality. The native icon is generated from `native/render-icon.swift`, packaged as a multi-resolution ICNS, and the app bundle is ad-hoc signed and verified.

A controlled three-model browser walkthrough confirmed Enter dispatch, collapsed proposal/review cards, the expanded final decision, smoke-tinted sent messages, and the untinted final answer. The API integration check also confirms the default collaborative path persists its selection to history.
