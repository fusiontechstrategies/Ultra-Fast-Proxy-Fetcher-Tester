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
