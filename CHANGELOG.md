# Changelog

All notable changes to this project are documented here.

## [2.0.0] - 2026-08-12

### Security

- Reject private, loopback, link-local, multicast, reserved, malformed, and invalid-port candidates before connection attempts.
- Require HTTPS source URLs, validate source DNS destinations, constrain redirects, verify TLS, and cap decompressed source responses.
- Replace the permissive Google HTTP test with a fixed HTTPS `204` connectivity check and disable redirect-based success.
- Bound fetch concurrency, check concurrency, per-request timeouts, response sizes, per-source endpoints, candidate counts, and worker creation.
- Ignore environment proxy settings and cookies for all application traffic.
- Contain untrusted network exceptions without exposing endpoint or exception details.

### Changed

- Rebuilt the network engine around asynchronous source fetching and a bounded proxy worker queue.
- Curated the source set from 88 entries to 52 sources confirmed to return candidates during the maintenance audit.
- Correctly normalize lists marketed as HTTPS proxies to HTTP CONNECT transport.
- Use accurate, separate source and proxy timing measurements.
- Atomically invalidate stale output before testing and replace it with the completed report, including zero-result reports.
- Require Python 3.10 or newer and reduce runtime dependencies to `aiohttp` and `aiohttp-socks`.
- Replace exaggerated fixed performance claims with measured per-run throughput.

### Added

- Fetch-only validation mode, protocol filtering, source concurrency controls, candidate limits, and configurable timeouts.
- Offline tests covering filtering, parsing, source safety, response limits, exact validation semantics, bounded concurrency, output integrity, and command-line bounds.
- GitHub Actions, dependency auditing, static analysis, typing, security linting, Dependabot, issue templates, contribution guidance, support guidance, and responsible-use documentation.
- Deterministic standalone, source ZIP, SPDX 2.3 SBOM, SHA-256 checksum, and commit-bound release-evidence construction.
- Tag-only automation that verifies a protected-main commit, attests the exact assets, and creates only a draft GitHub release.

### Distribution

- Pin the two direct runtime dependencies exactly for repeatable installation and SBOM identity.
- Build the same exact five assets twice and reject any filename or byte difference.
- Keep release publication, replacement, package-registry publication, and live proxy data outside the automated release path.

### Removed

- The bundled proxy snapshot and terminal screenshot containing potentially live third-party endpoints.
- Dead, empty, throttled, and consistently failing source entries.
- Unused `requests-futures`, `requests`, Pillow, and tqdm dependencies.

## [1.1.0] - 2026-03-09

- Added protocol-aware candidates and SOCKS4/SOCKS5 validation.
- Counted successful and redirected responses as valid.
- Added protocol summaries and protocol-qualified output.
- Added quiet mode and dependency documentation.
