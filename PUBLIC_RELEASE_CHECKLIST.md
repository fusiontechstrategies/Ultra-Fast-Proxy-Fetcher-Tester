# Public Release Checklist

## Source and data

- [ ] Remove generated proxy lists and screenshots containing real endpoints.
- [ ] Confirm no credentials, tokens, personal data, private URLs, or sensitive resource names exist in tracked files.
- [ ] Scan the complete Git history for secrets.
- [ ] Confirm every bundled example uses synthetic documentation addresses.
- [ ] Confirm the working tree is clean.

## Code quality and security

- [ ] Run the offline unit tests on every supported Python version.
- [ ] Pass Ruff linting and formatting checks.
- [ ] Pass strict mypy analysis.
- [ ] Pass Bandit security linting.
- [ ] Pass dependency installation and vulnerability audits.
- [ ] Complete a fetch-only live source validation.
- [ ] Complete a small, rate-limited live proxy smoke test against the fixed endpoint.

## Repository

- [ ] Add CI, Dependabot, issue templates, a pull-request template, and CODEOWNERS.
- [ ] Enable Issues, Discussions, vulnerability reporting, dependency alerts, secret scanning, push protection, and CodeQL.
- [ ] Add focused repository topics and a clear description.
- [ ] Protect `main` from force pushes and deletion.
- [ ] Require pull requests, conversation resolution, linear history, and passing checks.
- [ ] Confirm the license and community profile are detected by GitHub.
- [ ] Make the repository public only after every exposure audit passes.
