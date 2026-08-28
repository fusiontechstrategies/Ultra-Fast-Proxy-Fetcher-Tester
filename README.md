# Ultra-Fast Proxy Fetcher & Tester

[![CI](https://github.com/fusiontechstrategies/Ultra-Fast-Proxy-Fetcher-Tester/actions/workflows/ci.yml/badge.svg)](https://github.com/fusiontechstrategies/Ultra-Fast-Proxy-Fetcher-Tester/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Fetch, validate, rank, and save public HTTP, SOCKS4, and SOCKS5 proxy endpoints with one Python script. The engine uses bounded asynchronous concurrency, strict public-address filtering, and an end-to-end HTTPS connectivity check.

This project is intended for authorized network testing, software development, and research. Public proxies are untrusted. Never send credentials, personal information, proprietary data, or other sensitive traffic through an endpoint produced by this tool.

## Why this version is different

- Fetches concurrently from 52 curated HTTPS sources validated on 2026-08-12.
- Rejects private, loopback, link-local, multicast, reserved, malformed, and invalid-port entries before attempting a proxy connection.
- Validates HTTP CONNECT, SOCKS4, and SOCKS5 transports against a fixed HTTPS endpoint that must return exactly `204`.
- Blocks unsafe source URLs and redirects, verifies source TLS, checks DNS destinations, and caps decompressed response sizes.
- Uses bounded worker pools, source concurrency, timeouts, and a default 5,000-candidate safety cap.
- Caps every source at 5 MiB and 10,000 unique endpoints to constrain hostile or malformed feeds.
- Does not display third-party proxy addresses in live progress output.
- Atomically invalidates stale output before testing and replaces it with the completed report, including when no proxies work.
- Keeps all application logic in [`proxy_fetcher_ultimate.py`](proxy_fetcher_ultimate.py).

## Requirements

- Python 3.10 or newer
- Internet access to the configured source hosts and HTTPS connectivity endpoint

## Installation

```bash
git clone https://github.com/fusiontechstrategies/Ultra-Fast-Proxy-Fetcher-Tester.git
cd Ultra-Fast-Proxy-Fetcher-Tester
python -m venv .venv
```

Activate the environment on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

Install the runtime dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Usage

Run with safe defaults:

```bash
python proxy_fetcher_ultimate.py
```

Fetch and validate source data without testing or saving proxy endpoints:

```bash
python proxy_fetcher_ultimate.py --fetch-only
```

Test a smaller HTTP-only sample:

```bash
python proxy_fetcher_ultimate.py --protocol http --max-candidates 500 --concurrent 50
```

Choose a different output file and hide live progress:

```bash
python proxy_fetcher_ultimate.py --output results/proxies.txt --quiet
```

Show every option and its enforced bounds:

```bash
python proxy_fetcher_ultimate.py --help
```

Show the stable product version:

```bash
python proxy_fetcher_ultimate.py --version
```

### Important defaults

| Setting | Default | Enforced maximum |
|---|---:|---:|
| Proxy checks | 100 concurrent | 500 |
| Source downloads | 12 concurrent | 32 |
| Candidates tested | 5,000 | 50,000 |
| Proxy timeout | 8 seconds | 30 seconds |
| Source timeout | 12 seconds | 30 seconds |

Actual throughput depends on network conditions, operating-system limits, candidate quality, protocol mix, and timeout settings. The project deliberately makes no fixed checks-per-second promise.

## Output

Working endpoints are sorted by measured response time and grouped into speed categories. The following addresses are documentation-only examples and are never shipped as a usable proxy list:

```text
# LIGHTNING FAST (under 200ms)
http://192.0.2.10:8080              # 142.18ms

# VERY FAST (200-499ms)
socks5://198.51.100.20:1080         # 318.42ms
```

Generated proxy files are excluded by `.gitignore`. Treat them as transient operational data.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Completed successfully and, unless using `--fetch-only`, found at least one working proxy |
| `1` | Output or application failure |
| `2` | No valid public candidates were collected |
| `3` | Candidates were tested but none passed validation |
| `130` | Interrupted by the user |

## Security model and limitations

- The fixed HTTPS `204` check validates connectivity and TLS tunneling. It does not prove anonymity, trustworthiness, geographic location, uptime, or ownership.
- A proxy can become malicious or unavailable immediately after a successful test.
- Third-party source availability and content can change without notice.
- Source entries are data from independent projects. This repository does not redistribute a current proxy snapshot.
- The application ignores system proxy environment variables for source retrieval and test traffic.
- Adding custom target URLs is intentionally unsupported to reduce misuse and accidental traffic against third parties.

Read [SECURITY.md](SECURITY.md) for vulnerability reporting and [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md) before operating the tool.

## Release integrity

The `v2.0.0` release process is designed to contain exactly five files:

1. an exact standalone copy of `proxy_fetcher_ultimate.py`
2. a deterministic source and documentation ZIP
3. an SPDX 2.3 direct-dependency SBOM
4. `SHA256SUMS.txt`
5. commit-bound `release-evidence.json`

The builder uses a fixed file allowlist, canonical ZIP order, timestamps, permissions, and metadata. It rejects mismatched versions, tags, dependencies, source files, commits, or output sets. GitHub Actions builds the assets twice, compares every byte, exercises the exact standalone runtime without network access, and attests every asset before creating a draft. The workflow cannot publish the draft and does not publish to a package registry.

See [RELEASING.md](RELEASING.md) for the exact contract and [TESTING.md](TESTING.md) for offline, live, and release validation boundaries.

## Development

Install the development checks:

```bash
python -m pip install -r requirements-dev.txt
```

Run the same offline checks used by GitHub Actions:

```bash
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m mypy proxy_fetcher_ultimate.py
python -m bandit -q -r proxy_fetcher_ultimate.py
python -m pip_audit -r requirements.txt
python -m pip_audit -r requirements-dev.txt
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for source-review and pull-request requirements.

## License

Released under the [MIT License](LICENSE).
