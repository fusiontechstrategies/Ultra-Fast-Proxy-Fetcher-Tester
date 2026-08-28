# Testing guide

The project separates offline correctness checks, bounded live validation, and release-asset verification. Live network success is volatile and does not replace deterministic tests.

## Offline validation

Use Python 3.10 or newer in a clean virtual environment:

```bash
python -m pip install -r requirements-dev.txt
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m mypy proxy_fetcher_ultimate.py
python -m bandit -q -r proxy_fetcher_ultimate.py scripts
python -m pip_audit -r requirements.txt
python -m pip_audit -r requirements-dev.txt
```

The unit suite uses mocked network behavior and documentation-only addresses. It must not download or commit a proxy list.

## Bounded live validation

Run live checks only from an authorized network and only after reviewing [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md). Public feeds and proxy endpoints are untrusted, volatile third-party services.

Fetch-only validation exercises source TLS, DNS, redirect, response-size, parsing, and candidate filtering without connecting through discovered proxies or modifying the output file:

```bash
python proxy_fetcher_ultimate.py --fetch-only --fetch-concurrent 4 --source-timeout 8 --quiet
```

A release smoke test should use a small candidate cap and low concurrency against the fixed HTTPS `204` endpoint. Store the transient output outside the repository, do not print endpoint values in logs, and remove it after recording only aggregate results.

Live checks establish only that some sources or proxies responded during that run. They do not prove anonymity, ownership, safety, location, durability, or policy compliance.

### 2026-08-28 candidate record

The release-readiness tree completed a fresh bounded live check from an authorized maintenance environment:

- fetch-only: 52 of 52 configured HTTPS feeds usable in that run
- 45,927 unique candidates parsed, with 28 non-public or malformed entries rejected
- the default 5,000-candidate safety cap applied and no endpoint was tested or saved
- fixed-target smoke test: 25 HTTP candidates, five workers, six-second timeout
- 3 of 25 candidates returned the exact HTTPS `204` result
- aggregate response and failure counts were recorded without printing endpoint values
- the transient output containing the three live endpoints was deleted after the aggregate checks

These observations are time-specific readiness evidence, not an availability or performance promise.

## Release validation

Build the five assets twice with the exact candidate commit and commit timestamp. Require byte-identical output sets. Inspect every ZIP member and verify the standalone runtime matches source, the SBOM matches exact direct pins, checksums match, and evidence binds every artifact and ZIP member to the source commit.

Run `--version` and `--help` from the exact standalone asset without starting any fetch. Hosted CI performs the same release construction on Linux. An independent Windows build must match all five files byte for byte before the tag is approved.

The tag workflow creates only a draft. Downloaded draft and public assets require a new verification pass as described in [RELEASING.md](RELEASING.md).
