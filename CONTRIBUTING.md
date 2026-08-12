# Contributing

Contributions that improve correctness, safety, portability, testing, or documentation are welcome.

## Development setup

1. Fork the repository and create a focused branch.
2. Create a Python 3.10 or newer virtual environment.
3. Install `requirements-dev.txt`.
4. Make the smallest complete change.
5. Add or update offline tests.
6. Run every check documented in the README.
7. Open a pull request using the repository template.

## Source additions

A new source must:

- Use HTTPS without embedded credentials.
- Publish proxy data lawfully and permit automated access.
- Resolve only to public destinations.
- Stay below the application's response-size limit.
- Declare the correct HTTP CONNECT, SOCKS4, or SOCKS5 transport.
- Return enough valid public endpoints to justify the maintenance cost.
- Avoid requiring authentication, tokens, browser automation, or anti-bot bypasses.

Do not commit downloaded proxy lists, real proxy endpoints, screenshots containing endpoints, credentials, or live operational results. Tests must use synthetic documentation addresses and mocked network behavior.

## Pull requests

Pull requests should explain the user-visible behavior, security implications, tests performed, and documentation changes. All continuous-integration checks must pass before merge.

By contributing, you agree that your contribution is licensed under the repository's MIT License.
