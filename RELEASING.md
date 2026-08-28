# Release process

Ultra-Fast Proxy Fetcher and Tester releases come from a reviewed, fully tested commit on protected `main`. Runtime identity, changelog, release notes, dependency pins, tag, assets, checksums, SBOM, and evidence must describe the same stable version.

Creating a tag and publishing a GitHub release each require an explicit maintainer decision. The tag workflow can create only a draft. It contains no release-publication or package-registry command.

## Exact asset contract

For version `X.Y.Z`, a GitHub release contains only:

1. `Ultra-Fast-Proxy-Fetcher-Tester-vX.Y.Z.py`
2. `Ultra-Fast-Proxy-Fetcher-Tester-vX.Y.Z.zip`
3. `Ultra-Fast-Proxy-Fetcher-Tester-vX.Y.Z.spdx.json`
4. `SHA256SUMS.txt`
5. `release-evidence.json`

The standalone and ZIP runtime are byte-identical to `proxy_fetcher_ultimate.py` in the tagged commit. The stored ZIP has a fixed allowlist, canonical order, timestamps, permissions, and member metadata. It contains no generated proxy list or live endpoint result. The SPDX 2.3 document records the exact direct runtime dependencies. SHA-256 covers the runtime, ZIP, and SBOM. Machine-readable evidence binds those assets and every ZIP member to the exact source commit.

Every release asset receives GitHub build-provenance attestation. Existing release assets are never replaced.

## Release-readiness gates

1. Start from current protected `main`.
2. Confirm runtime `VERSION`, changelog heading, and `.github/release-notes/vX.Y.Z.md` agree.
3. Run all offline tests on Python 3.10, 3.12, and 3.14 and the platform suite on Windows and macOS.
4. Pass Ruff, formatting, mypy, Bandit, dependency audits, CodeQL, Semgrep, Trivy, dependency review, and full-history Gitleaks.
5. Build the exact five assets twice with the candidate commit and commit time, then require identical filenames and bytes.
6. Run `--version` and `--help` from the standalone asset without network access.
7. Inspect every ZIP path, byte, timestamp, mode, and metadata field; verify checksums, SBOM dependencies, and commit-bound evidence.
8. Confirm no generated proxy list, live endpoint result, credential, sensitive log, or local path appears in any asset.
9. Complete a fresh fetch-only check and one small, rate-limited smoke test from an authorized network. Record aggregate results only.

## Candidate command

Use a new output directory and the exact 40-character candidate commit:

```powershell
$candidateCommit = git rev-parse HEAD
$candidateEpoch = git show -s --format=%ct HEAD

python scripts\prepare_release.py `
  --version 2.0.0 `
  --tag v2.0.0 `
  --source-commit $candidateCommit `
  --source-date-epoch $candidateEpoch `
  --output-directory release-assets
```

The builder fails closed on a mismatched version, tag, changelog, release notes file, dependency pin, source file, commit, output directory, archive path, ZIP field, or final asset set.

## Draft creation

Tag creation is maintainer-controlled. The tag must be `vX.Y.Z` and resolve to the approved protected-main commit. That commit must be GitHub-verified and reachable from protected `main`.

Pushing the tag starts `.github/workflows/release.yml`. The workflow:

1. validates the tag and exact commit
2. refuses to continue if a release already exists
3. builds the five files twice and compares every byte
4. exercises the exact standalone runtime without network access
5. attests every asset with GitHub provenance
6. creates a non-prerelease draft from committed versioned notes
7. confirms the draft contains exactly the five approved files

The workflow has no manual trigger and no publication command.

## Publication review

Before publishing the draft:

- confirm the tag and draft target the approved verified commit
- download all five assets into a new directory
- recompute every SHA-256 digest and verify every provenance attestation
- confirm the standalone and ZIP runtime bytes match tagged source
- inspect the complete portable ZIP allowlist and metadata
- confirm the SPDX dependency set and commit-bound evidence
- run `--version` and `--help` from the downloaded standalone asset without network access
- rerun the complete offline checks
- perform the bounded live validation from [TESTING.md](TESTING.md) without logging endpoint values
- confirm zero open code-scanning, Dependabot, or secret-scanning alerts
- confirm release notes retain the authorization, fixed-target, untrusted-proxy, and sensitive-data boundaries

Publish only after every check passes. Then repeat the public download, digest, provenance, runtime, ZIP, offline, and bounded live verification against the public URLs.

## Registry publication remains separate

This repository has no PyPI or other registry publication workflow. Any future registry work requires a separate package identity, packaging, trusted publisher, protected environment, and clean-install review. Never add a long-lived registry token merely to simplify publication.
