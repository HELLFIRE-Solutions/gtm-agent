"""Assemble the tree the gate runs the tests in (stdlib only).

Inputs are two checked-out trees: ``--base`` (the target branch commit, trusted)
and ``--pr`` (the pull request head, untrusted).  The output tree contains

* the pull request's files, except protected paths;
* every protected path exactly as it is on base (so existing tests,
  ``conftest.py``, ``pyproject.toml``, pytest configuration and ``.github/**``
  are base's; a protected path the PR adds is dropped, one the PR deletes is
  restored);
* new files the PR adds under ``tests/`` (these are not protected).

The script is always executed from the base checkout.  It never imports or
executes anything from the PR tree.  A JSON report describing the changes is
written for the summary step.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import shutil
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import safe, write_json  # noqa: E402
from protected import TESTS_DIR, classify, new_src_toplevel, protected_reason  # noqa: E402

PYPROJECT = "pyproject.toml"
DIFF_LINE_LIMIT = 120


class AssembleError(Exception):
    """The PR cannot be assembled safely; ``report`` holds what is known."""

    def __init__(self, errors: list[str], report: dict | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.report = report or {}


# --------------------------------------------------------------------------- scan


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(root: str) -> dict[str, tuple[str, str]]:
    """Map relative POSIX path -> ("file", sha256) or ("link", target).

    Symlinks are recorded, never followed.  ``.git`` is ignored.  Empty
    directories and special files are ignored.
    """
    root = os.fspath(root)
    entries: dict[str, tuple[str, str]] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        rel_dir = os.path.relpath(dirpath, root)
        prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
        for name in dirnames + filenames:
            if name == ".git":
                continue
            full = os.path.join(dirpath, name)
            rel = prefix + name
            mode = os.lstat(full).st_mode
            if stat.S_ISLNK(mode):
                entries[rel] = ("link", os.readlink(full))
            elif stat.S_ISREG(mode):
                entries[rel] = ("file", _sha256(full))
    # os.walk does not descend into symlinked dirs but lists them in dirnames;
    # they were handled by the S_ISLNK branch above and are not walked further.
    return entries


def diff_trees(base: dict, pr: dict) -> dict[str, str]:
    """Changed paths: path -> "added" | "modified" | "deleted"."""
    changes: dict[str, str] = {}
    for path in sorted(set(base) | set(pr)):
        if path not in base:
            changes[path] = "added"
        elif path not in pr:
            changes[path] = "deleted"
        elif base[path] != pr[path]:
            changes[path] = "modified"
    return changes


# ---------------------------------------------------------------------- symlinks


def check_symlinks(pr_root: str, pr_entries: dict, changes: dict, base_paths) -> list[str]:
    """Error messages for PR-introduced symlinks that are not acceptable.

    A symlink the PR adds or retargets is rejected when it sits in a protected
    path, anywhere under ``tests/``, has an absolute target, or resolves
    outside the PR tree.
    """
    errors: list[str] = []
    root_real = os.path.realpath(pr_root)
    for path, status in sorted(changes.items()):
        if status == "deleted":
            continue
        kind, target = pr_entries[path]
        if kind != "link":
            continue
        shown = safe(path)
        reason = protected_reason(path, base_paths)
        if reason:
            errors.append("symlink in protected path: %s (%s)" % (shown, reason))
        elif path.split("/")[0] == TESTS_DIR:
            errors.append("symlink under tests/: %s" % shown)
        if os.path.isabs(target):
            errors.append("symlink with absolute target: %s -> %s" % (shown, safe(target)))
            continue
        real = os.path.realpath(os.path.join(pr_root, *path.split("/")))
        if not (real == root_real or real.startswith(root_real + os.sep)):
            errors.append("symlink points outside the tree: %s -> %s" % (shown, safe(target)))
    return errors


# ------------------------------------------------------------------------- copy


def _place(out_root: str, rel: str, src_root: str, entry: tuple[str, str]) -> None:
    """Copy one entry into the output tree, replacing whatever is in the way."""
    parts = rel.split("/")
    cur = out_root
    for part in parts[:-1]:
        cur = os.path.join(cur, part)
        if os.path.islink(cur) or (os.path.lexists(cur) and not os.path.isdir(cur)):
            os.remove(cur)
        os.makedirs(cur, exist_ok=True)
    dest = os.path.join(cur, parts[-1])
    if os.path.lexists(dest):
        if os.path.isdir(dest) and not os.path.islink(dest):
            shutil.rmtree(dest)
        else:
            os.remove(dest)
    kind, target = entry
    if kind == "link":
        os.symlink(target, dest)
    else:
        shutil.copy2(os.path.join(src_root, *parts), dest)


def find_pytest_config(root: str) -> str | None:
    """The pytest configuration file at ``root``, using pytest's own precedence."""

    def read(name: str) -> str:
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return ""

    for name in ("pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml"):
        if os.path.isfile(os.path.join(root, name)):
            return name
    if "[tool.pytest" in read(PYPROJECT):
        return PYPROJECT
    if "[pytest]" in read("tox.ini"):
        return "tox.ini"
    if "[tool:pytest]" in read("setup.cfg"):
        return "setup.cfg"
    return None


def _pyproject_diff(base_root: str, pr_root: str) -> list[str]:
    def read(root: str) -> list[str]:
        try:
            with open(os.path.join(root, PYPROJECT), encoding="utf-8", errors="replace") as fh:
                return fh.read().splitlines()
        except OSError:
            return []

    diff = list(
        difflib.unified_diff(
            read(base_root), read(pr_root), "base/pyproject.toml", "pr/pyproject.toml", lineterm="", n=1
        )
    )
    if len(diff) > DIFF_LINE_LIMIT:
        diff = diff[:DIFF_LINE_LIMIT] + ["... (%d more lines)" % (len(diff) - DIFF_LINE_LIMIT)]
    return diff


# ---------------------------------------------------------------------- assemble


def assemble(base_root: str, pr_root: str, out_root: str) -> dict:
    """Build ``out_root`` and return the report.  Raises AssembleError."""
    if os.path.lexists(out_root) and os.listdir(out_root):
        raise AssembleError(["output directory is not empty: %s" % safe(out_root)])

    base_entries = scan(base_root)
    pr_entries = scan(pr_root)
    base_paths = frozenset(base_entries)
    changes = diff_trees(base_entries, pr_entries)
    cls = classify(changes, base_paths)

    report: dict = {
        "changes": changes,
        "classification": cls.as_dict(),
        "new_src_toplevel": new_src_toplevel(base_paths, pr_entries),
        "pyproject_diff": _pyproject_diff(base_root, pr_root) if PYPROJECT in changes else [],
        "errors": [],
    }

    errors = check_symlinks(pr_root, pr_entries, changes, base_paths)
    if errors:
        report["errors"] = errors
        raise AssembleError(errors, report)

    os.makedirs(out_root, exist_ok=True)
    for path in sorted(pr_entries):
        if protected_reason(path, base_paths) is None:
            _place(out_root, path, pr_root, pr_entries[path])
    for path in sorted(base_entries):
        if protected_reason(path, base_paths) is not None:
            _place(out_root, path, base_root, base_entries[path])

    config = find_pytest_config(out_root)
    if config is None:
        # No pytest configuration on base: use an explicit empty one so pytest
        # cannot pick up an ini file that sits next to the collected tests.
        config = "pytest.ini"
        for root in (out_root, base_root):
            with open(os.path.join(root, config), "w", encoding="utf-8") as fh:
                fh.write("[pytest]\n")
    report["pytest_config"] = config
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="trusted base checkout")
    ap.add_argument("--pr", required=True, help="untrusted PR head checkout")
    ap.add_argument("--out", required=True, help="directory to assemble (must be empty)")
    ap.add_argument("--report", required=True, help="path of the JSON report to write")
    args = ap.parse_args(argv)

    try:
        report = assemble(args.base, args.pr, args.out)
    except AssembleError as exc:
        report = dict(exc.report)
        report["errors"] = exc.errors
        write_json(args.report, report)
        print("ASSEMBLE FAILED:")
        for err in exc.errors:
            print("  - " + safe(err))
        return 1

    write_json(args.report, report)
    config_file = os.path.join(os.path.dirname(os.path.abspath(args.report)), "pytest-config.txt")
    with open(config_file, "w", encoding="utf-8") as fh:
        fh.write(report["pytest_config"] + "\n")

    cls = report["classification"]
    print("changed files: %d" % len(report["changes"]))
    print("protected paths touched: %d (base version used)" % (
        len(cls["protected_modified"]) + len(cls["protected_deleted"])))
    print("new tests: %d" % len(cls["tests_added"]))
    print("pytest config: " + safe(report["pytest_config"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
