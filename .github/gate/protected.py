"""Protected paths and classification of a pull request's changed files.

A path is *protected* when its content decides how the gate itself runs
(workflow definitions, pytest/build configuration, ``conftest.py``) or when it
is an existing test.  In the assembled tree every protected path comes from the
base commit, whatever the pull request contains.

All paths are POSIX-style, relative to the repository root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

TESTS_DIR = "tests"

# Any path component with one of these names marks the whole subtree protected.
PROTECTED_DIR_NAMES = frozenset({".github", ".claude"})

# Files protected at any depth.
PROTECTED_BASENAMES = frozenset({"conftest.py", "CLAUDE.md", "pyproject.toml"})

# pytest / build configuration files; protected at any depth because pytest
# discovers ini files from the directories of the collected arguments.
CONFIG_BASENAMES = frozenset(
    {
        "pytest.ini",
        ".pytest.ini",
        "pytest.toml",
        ".pytest.toml",
        "tox.ini",
        "setup.cfg",
        "MANIFEST.in",
    }
)

# Root-level modules (setup.py, sitecustomize.py, a module shadowing a
# dependency, ...) and .pth files are importable from the test process.
ROOT_CODE_SUFFIXES = (".py", ".pth")

STATUSES = ("added", "modified", "deleted")


def protected_reason(path: str, base_paths: Iterable[str]) -> str | None:
    """Why ``path`` is protected, or ``None`` if it is not."""
    parts = path.split("/")
    name = parts[-1]
    if not isinstance(base_paths, (set, frozenset)):
        base_paths = frozenset(base_paths)
    if any(p in PROTECTED_DIR_NAMES for p in parts):
        return "workflow/agent configuration (.github/**, .claude/**)"
    if name in PROTECTED_BASENAMES:
        return "gate-relevant file (%s)" % name
    if name in CONFIG_BASENAMES:
        return "pytest/build configuration (%s)" % name
    if len(parts) == 1 and name.endswith(ROOT_CODE_SUFFIXES):
        return "root-level module importable by the test process"
    if parts[0] == TESTS_DIR and path in base_paths:
        return "test file that exists on base"
    return None


@dataclass
class Classification:
    protected_modified: list[str] = field(default_factory=list)  # edited or added
    protected_deleted: list[str] = field(default_factory=list)
    tests_added: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    # Subsets / details of the lists above, for reporting.
    protected_added: list[str] = field(default_factory=list)
    tests_modified: list[str] = field(default_factory=list)  # existing base tests edited
    tests_deleted: list[str] = field(default_factory=list)  # existing base tests removed
    reasons: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: (sorted(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()}


def classify(changes: Mapping[str, str], base_paths: Iterable[str]) -> Classification:
    """Sort a PR's changed files.

    ``changes`` maps path -> "added" | "modified" | "deleted".
    """
    base = frozenset(base_paths)
    result = Classification()
    for path in sorted(changes):
        status = changes[path]
        if status not in STATUSES:
            raise ValueError("unknown change status %r for %r" % (status, path))
        reason = protected_reason(path, base)
        if reason is None:
            if status == "added" and path.split("/")[0] == TESTS_DIR:
                result.tests_added.append(path)
            else:
                result.other.append(path)
            continue
        result.reasons[path] = reason
        is_base_test = path.split("/")[0] == TESTS_DIR and path in base
        if status == "deleted":
            result.protected_deleted.append(path)
            if is_base_test:
                result.tests_deleted.append(path)
        else:
            result.protected_modified.append(path)
            if status == "added":
                result.protected_added.append(path)
            elif is_base_test:
                result.tests_modified.append(path)
    return result


def new_src_toplevel(base_paths: Iterable[str], pr_paths: Iterable[str]) -> list[str]:
    """Top-level names under ``src/`` that the PR introduces.

    A new top-level package is installed next to the dependencies and can
    shadow one of them, so the summary points it out.
    """

    def tops(paths: Iterable[str]) -> set[str]:
        return {p.split("/")[1] for p in paths if p.startswith("src/") and p.count("/") >= 2}

    return sorted(tops(pr_paths) - tops(base_paths))
