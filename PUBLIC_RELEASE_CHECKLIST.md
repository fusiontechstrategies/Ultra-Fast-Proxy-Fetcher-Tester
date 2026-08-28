# Public Release Checklist

## Source and data

- [x] Remove generated proxy lists and screenshots containing real endpoints.
- [x] Confirm no credentials, tokens, personal data, private URLs, or sensitive resource names exist in tracked files.
- [x] Scan the complete Git history for secrets.
- [x] Confirm every bundled example uses synthetic documentation addresses.
- [x] Confirm the working tree is clean.

## Code quality and security

- [x] Run the offline unit tests on every supported Python version.
- [x] Pass Ruff linting and formatting checks.
- [x] Pass strict mypy analysis.
- [x] Pass Bandit security linting.
- [x] Pass dependency installation and vulnerability audits.
- [x] Complete a fetch-only live source validation.
- [x] Complete a small, rate-limited live proxy smoke test against the fixed endpoint.

## Repository

- [x] Add CI, Dependabot, issue templates, a pull-request template, and CODEOWNERS.
- [x] Enable Issues, Discussions, vulnerability reporting, dependency alerts, secret scanning, push protection, and CodeQL.
- [x] Add focused repository topics and a clear description.
- [x] Protect `main` from force pushes and deletion.
- [x] Require pull requests, conversation resolution, linear history, and passing checks.
- [x] Confirm the license and community profile are detected by GitHub.
- [x] Make the repository public only after every exposure audit passes.

## Distribution readiness

- [x] Pin direct runtime and development dependencies exactly.
- [x] Build the standalone runtime, deterministic ZIP, SPDX 2.3 SBOM, SHA-256 checksums, and commit-bound evidence.
- [x] Require exactly five release assets and reject existing output directories or nonportable archive paths.
- [x] Prove repeat builds are byte-identical and the standalone runtime is byte-identical to tagged source.
- [x] Exercise `--version` and `--help` from the exact standalone asset without network access.
- [x] Add GitHub build-provenance attestations for every release asset.
- [x] Restrict release automation to a verified tag commit reachable from protected `main`.
- [x] Allow the tag workflow to create only a non-prerelease draft.
- [x] Keep live proxy endpoints and generated results out of every asset.

## Publication gate

- [ ] Obtain explicit authorization for the exact `v2.0.0` tag and target commit.
- [ ] Inspect the generated draft, download all five assets, and verify every digest and attestation.
- [ ] Recheck the complete ZIP allowlist, metadata, source bytes, SBOM dependencies, and release evidence.
- [ ] Rerun offline checks and a fresh, small, rate-limited live validation from the downloaded source.
- [ ] Confirm zero open code-scanning, Dependabot, or secret-scanning alerts.
- [ ] Publish the reviewed draft, then verify the public downloads without replacing any asset.
