# Contributing

Create and activate a virtual environment as shown in the [README](README.md).
Install the development dependencies with `python -m pip install -e '.[dev]'`, then run
`ruff check .`, `ruff format --check .`, and `pytest` before opening a pull request.
`pre-commit install` enables the same formatting and basic file checks locally.

Include a regression test for behavior changes and update examples when the public
API changes. Tests should use mock providers rather than paid API calls. Describe
any security limitations in the pull request; avoid claims that a heuristic
prevents all attacks.

For packaging changes, run `python -m build` and `python -m twine check dist/*`.
Then run `python scripts/check_package.py dist/*.whl` to install the wheel in a
clean environment and check the API and CLI without optional provider SDKs.
CI runs the suite on Python 3.10 through 3.15 with a coverage floor of 85%; the
required `test` check only passes when every runtime succeeds.
Releases use `.github/workflows/publish.yml`. Publish a GitHub release with a
`v<version>` tag matching `pyproject.toml`; the tagged commit must be reachable
from `main`. The workflow tests and builds packages before requesting approval
through the `pypi-publish` environment. Its separate publish job receives the
`PYPI_API_TOKEN` secret and only uploads the artifacts from that build.

CodeQL scans Python and workflow files on pull requests, updates to `main`, and a
weekly schedule. Dependabot checks Python dependencies and Actions versions weekly.
Workflow changes take effect once they reach GitHub; local checks do not replace
the required checks or reviews configured on the repository.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
