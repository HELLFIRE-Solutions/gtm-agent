# Merge gate

`.github/workflows/gate.yml` runs on `pull_request_target` for PRs against
`main`. GitHub reads the workflow definition from the base branch, so a PR
cannot change its own gate. The scripts in this folder are stdlib-only
Python and are always run from the checkout of the base commit (`base/`);
the PR head is checked out into `pr/` and treated as data.

## Jobs

- `tests` – assemble the tree, install, run pytest on base and on the
  assembled tree, compute the verdict, write the job summary.
- `owner-approval` – `needs: tests`, bound to the `owner-gate` environment
  (required reviewer configured in repository settings). It prints the head
  SHA and does nothing else; the reviewer's approval of the pending
  deployment is the decision.

Both job names are meant to be required status checks on `main`.

## Scripts

| script | what it does |
| --- | --- |
| `assemble.py` | Builds the tree the tests run in (rules below) and writes `assemble.json` and `pytest-config.txt`. |
| `protected.py` | Defines protected paths and classifies a PR's changed files. |
| `verdict.py` | Compares the JUnit report of the gate run with the JUnit report of the run on base. |
| `summary.py` | Renders the Markdown job summary. |
| `common.py` | Escaping helpers so PR-controlled strings cannot start workflow commands or inject Markdown. |

### Assembled tree

- Files from the PR, except protected paths.
- Protected paths are taken from base: absent on base means absent in the
  tree, deleted by the PR means restored. Protected are: `.github/**`,
  `.claude/**`, `CLAUDE.md`, `pyproject.toml`, `conftest.py` at any depth,
  pytest/build configuration files (`pytest.ini`, `tox.ini`, `setup.cfg`,
  `MANIFEST.in`, ... at any depth), root-level `*.py` / `*.pth` files, and
  every file that exists under `tests/` on base.
- New files the PR adds under `tests/` are included (except protected ones
  such as `conftest.py`).
- A symlink the PR adds or retargets is rejected if it points outside the
  tree, has an absolute target, sits in a protected path or anywhere under
  `tests/`. Symlinks are never followed while scanning or copying.
- The project is installed non-editable from the assembled tree, so the
  build configuration and dependency list are base's. pytest is run with an
  explicit `-c` pointing at base's configuration (an empty `pytest.ini` is
  created when base has none), so an ini file placed next to new tests is
  not picked up.

### `pyproject.toml` policy

A PR's `pyproject.toml` is never used in the gate run. The change is listed
under protected paths in the summary together with a diff. Consequently a PR
that needs a new dependency fails its own tests; the dependency change has to
land first as a PR that touches only `pyproject.toml` (the gate stays green
because base's file is used), followed by the PR that uses it.

### Verdict

The gate passes only if every test id present in the base run has outcome
`passed` in the gate run. An id that is `skipped` or `xfailed` on base passes
if it has the same outcome in the gate run. A base id that is missing,
skipped, xfailed, failed or errored fails the gate and is named. A new test
that fails (including a collection error) also fails the gate, and a run with
no tests fails.

## Guarantees

For a PR that only changes source files and adds ordinary test files: the
tests that exist on base run unmodified, with base's pytest configuration and
base's dependency list, against the PR's source, and each must pass.
Editing or deleting an existing test, `conftest.py`, pytest configuration,
`pyproject.toml` or the workflow has no effect on the gate run, and the
summary lists every such change.

## Not guaranteed

- Code in the PR's source runs inside the pytest process and in the same job
  as the gate scripts. Malicious source can alter the JUnit report, write to
  `GITHUB_ENV` / `GITHUB_PATH`, or otherwise misreport. The gate catches
  weakened tests, not hostile code; the human decision is the backstop.
- A new test file runs with the full power of Python: it can monkeypatch
  modules so existing tests pass for the wrong reason. New tests are listed in
  the summary but their quality is not judged.
- New non-test helper files under `tests/` (for example a module named like
  a dependency) are included and can shadow imports in the test process.
- A new top-level package under `src/` is installed next to the
  dependencies and can shadow one of them; the summary lists such entries.
- A test that is skipped for environmental reasons on base is accepted as
  skipped in the gate run.
- The PR is compared with `base.sha` from the event, not with a merge result.
  A PR that is behind `main` shows main's newer changes as its own; require
  branches to be up to date before merge.
- Another workflow in the PR could report a check with the same name as the
  required ones; which one branch protection trusts is a GitHub behaviour this
  repository cannot control.
- Dependencies are installed from the package index at run time; their
  contents are as trusted as the index.
