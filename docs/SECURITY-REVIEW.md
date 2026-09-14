# Cleanup and security review — 2026-09-14

This is a source review and regression/advisory check, not a penetration test, security certification, guarantee against compromise, or legal finding about responsibility.

## Corrections

- Removed two unused imports, an unused ranking argument, and a redundant API-route condition. The dead-code scan's remaining high-confidence reports are required classmethod receiver parameters in Pydantic validators, not removable functionality. There are no extra local feature branches; only `main` and its remote tracking refs were present. Reachable API compatibility paths were preserved.
- Deleting a connection now deletes its permission override, preventing a reused ID from inheriting a stale grant.
- Grok native image generation explicitly denies MCP tool execution in addition to limiting image tools.
- Unicode media credentials now receive an authentication rejection instead of raising a string-comparison server error.
- Debate does not count oversized/truncated or conflicting explicit assent as consensus.
- CLI process-group cleanup kills remaining descendants after a parent exits; text and image adapters share that cleanup. Processes deliberately escaping their group under full access are outside this containment.
- Installed wheels default the working folder to the launch directory instead of `site-packages`; source checkouts retain the repository default.

## Dependencies and distribution

Runtime, bootstrap and development lockfiles pin versions and SHA-256 hashes. Recommended clone installation and Debian setup verify hashes, accept wheels only, and install BorgNet without unpinned build-isolation dependencies. The direct dependency minimums now reflect the tested runtime versions. Ordinary `pip install .` still resolves supported ranges; use the documented lockfile installation for reproducibility.

`pip-audit` reported **zero known vulnerabilities in 65 unique pinned versions**, including inactive platform variants such as Windows-only dependencies. The installed environment check returned 38 entries and no findings; the runtime-only lock audit returned 31 entries and no findings. Advisory lookup reported no skipped packages in those reports. This does not detect unknown vulnerabilities or prove upstream packages harmless.

GitHub Actions now checks hash-pinned installation, dependency consistency, lint, tests and all-platform advisory results. Action dependencies are pinned to verified commit SHAs with read-only repository permissions. A weekly audit workflow and Dependabot configuration are included. These checks become active only after publication to GitHub and subject to repository Actions settings; no remote run is claimed here.

## Verification

- 95 Python regression tests pass on Python 3.14. A fresh, hash-pinned Python 3.11 installation is tested separately.
- A separate runtime-only Python 3.11 environment successfully installed the hash-pinned bootstrap/runtime packages and built/installed the project with dependency resolution and build isolation disabled; `pip check` passed.
- All frontend JavaScript files parse; keyboard submission and model-option switching tests pass.
- Ruff unused-import/undefined-name checks pass. Pattern scanning of 70 source/distribution configuration files found no private-key or common credential-token matches. This is not exhaustive secret detection or a new full-history scan.
- Debian archive tests check reproducibility, bundled lockfiles, hash-verifying launcher arguments and absence of private configuration. No Debian desktop runtime or Windows runtime test was performed on this Mac.

## Remaining boundaries

The app is for a trusted single-user machine. Keep it on loopback and do not expose it through a public proxy. Private browser authentication and write tokens remain required. Model output is rendered as text; provider credentials remain in headers and owner-only files; provider redirects and environment proxies remain disabled.

Full CLI access intentionally permits commands, files and network access as the current user without per-command approval. Consensus is not a security boundary or proof of correctness. Prompt injection remains a risk when granting an agent tools. Installed CLIs, their local configuration/plugins, MCP programs, model servers, provider services, browsers and the OS require separate maintenance and are not covered by the Python dependency audit. Secret-pattern and advisory scans cannot rule out all compromises.

The changes are local until committed and pushed. Rebuild distribution artifacts and restart existing server processes to apply code changes; old clones and already-running processes do not update themselves.

## Browser/desktop adapter addition

The installer now includes Playwright Chromium setup and local stdio automation adapters. Browser and desktop grants default off, require Full CLI access and expire with the request. Every control tool rechecks the grant. Desktop OS consent is checked without attempting to change it; Wayland/Windows desktop control is unavailable. A fixed offline browser self-test accepts no user-supplied URL or actions and does not enable model permissions. Browser/desktop observations can contain sensitive data; full CLI privileges and model correctness remain outside this gate's guarantees. New dependencies were hash-pinned and re-audited with no known vulnerabilities reported. Desktop clicks/typing were not exercised against the user's actual applications.
