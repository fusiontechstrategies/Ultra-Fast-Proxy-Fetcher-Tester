# Security Policy

## Supported version

Security updates are applied to the latest code on `main`.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature on the repository Security page. Do not open a public issue for a suspected vulnerability, source-safety bypass, credential exposure, or other sensitive report.

Include:

- The affected version or commit.
- Clear reproduction steps.
- The expected and observed behavior.
- The security impact.
- Any suggested mitigation.

Please allow a reasonable period for investigation and remediation before public disclosure.

## Threat model

The project treats proxy endpoints and source content as hostile input. Controls include public-address filtering, HTTPS-only source retrieval, DNS destination checks, redirect limits, body-size limits, bounded concurrency, strict timeouts, exact HTTPS validation, atomic output, and redacted aggregate progress.

These safeguards cannot make a public proxy trustworthy. Never use discovered endpoints for sensitive traffic.

Each source deadline covers preflight DNS, all redirects, and response-body
consumption after its concurrency slot is acquired. DNS uses a bounded isolated
child process that is killed and reaped on timeout or cancellation. This avoids
an orphaned system-resolver executor holding CLI shutdown beyond the deadline.

Release builds install a complete artifact-hash lock. Clean later jobs verify
exact installation member manifests, RECORD digests, reviewed build inputs,
metadata and entry points before attestation. Publication runs workflow-reviewed
verification code rather than code from the selected release tag. Both the
publication copy and its immutable transfer are checked against the original
attested wheel and source archive hashes immediately before publishing.
