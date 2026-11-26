"""Markdown job summary for the gate (stdlib only).

Reads the assemble report and the verdict written by the earlier steps and
prints Markdown on stdout.  Missing inputs are tolerated, so the summary is
still produced when an earlier step failed.  Every PR-controlled string is
rendered as an inline code span.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import md_code, read_json  # noqa: E402

LIST_LIMIT = 40


def _bullets(items, fmt=md_code) -> list[str]:
    items = list(items)
    lines = ["- " + fmt(i) for i in items[:LIST_LIMIT]]
    if len(items) > LIST_LIMIT:
        lines.append("- ... and %d more" % (len(items) - LIST_LIMIT))
    return lines


def _load(path: str | None):
    if not path:
        return None
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def render(report: dict | None, verdict: dict | None, head_sha: str, base_sha: str) -> str:
    out: list[str] = ["## Gate summary", ""]
    out.append("- Head commit under review: %s" % md_code(head_sha or "unknown", 64))
    out.append("- Base commit: %s" % md_code(base_sha or "unknown", 64))
    out.append("")

    # ---- verdict -----------------------------------------------------------
    if verdict is None:
        out += ["**Tests: no verdict was produced** (an earlier step failed).", ""]
    elif verdict.get("error"):
        out += ["**Tests: FAIL** - %s" % md_code(verdict["error"]), ""]
    elif verdict.get("passed"):
        out += ["**Tests: PASS** - every test that exists on base passed.", ""]
    else:
        out += ["**Tests: FAIL**", ""]

    # ---- assemble errors ---------------------------------------------------
    if report is None:
        out += ["No assemble report is available.", ""]
        report = {}
    if report.get("errors"):
        out += ["### Rejected by the assemble step", ""]
        out += _bullets(report["errors"])
        out.append("")

    cls = report.get("classification") or {}
    changes = report.get("changes") or {}
    counts = {s: sum(1 for v in changes.values() if v == s) for s in ("added", "modified", "deleted")}
    out += [
        "### Files changed: %d" % len(changes),
        "",
        "- added: %d, modified: %d, deleted: %d" % (counts["added"], counts["modified"], counts["deleted"]),
        "- other (unprotected) files: %d" % len(cls.get("other", [])),
        "",
    ]

    # ---- protected paths ---------------------------------------------------
    touched = list(cls.get("protected_modified", [])) + list(cls.get("protected_deleted", []))
    if touched:
        out += [
            "### PROTECTED PATHS TOUCHED: %d" % len(touched),
            "",
            "These paths are taken from the base commit in the gate run; the PR's "
            "version was not used. A human should review each one.",
            "",
        ]
        reasons = cls.get("reasons", {})
        for path in sorted(touched):
            how = "deleted" if path in cls.get("protected_deleted", []) else changes.get(path, "changed")
            out.append("- %s - %s (%s)" % (md_code(path), how, md_code(reasons.get(path, ""), 120)))
        out.append("")
    else:
        out += ["### Protected paths touched: none", ""]

    if report.get("pyproject_diff"):
        out += ["### pyproject.toml differs from base (not applied in the gate run)", "", "```diff"]
        out += [line.replace("```", "'''") for line in report["pyproject_diff"]]
        out += ["```", ""]

    if report.get("new_src_toplevel"):
        out += ["### New top-level entries under src/", ""]
        out += _bullets(report["new_src_toplevel"])
        out.append("")

    # ---- tests -------------------------------------------------------------
    out += ["### Tests in this PR", ""]
    out.append("- added: %d" % len(cls.get("tests_added", [])))
    out.append("- existing tests modified (base version used): %d" % len(cls.get("tests_modified", [])))
    out.append("- existing tests deleted (restored from base): %d" % len(cls.get("tests_deleted", [])))
    for title, key in (
        ("Added", "tests_added"),
        ("Modified", "tests_modified"),
        ("Deleted", "tests_deleted"),
    ):
        if cls.get(key):
            out += ["", "%s:" % title]
            out += _bullets(cls[key])
    out.append("")

    # ---- base ids vs gate results -----------------------------------------
    if verdict and not verdict.get("error"):
        out += [
            "### Base test ids vs gate results",
            "",
            "- tests on base: %d" % verdict.get("base_total", 0),
            "- of those passed in the gate run: %d" % verdict.get("base_passed_in_gate", 0),
            "- skipped/xfailed on base and the same in the gate run: %d" % verdict.get("base_same_nonrun", 0),
            "- missing from the gate run: %d" % len(verdict.get("missing", [])),
            "- did not pass: %d" % len(verdict.get("not_passed", {})),
            "- tests in the gate run: %d (new: %d, new and failed: %d)" % (
                verdict.get("gate_total", 0), verdict.get("new_total", 0), len(verdict.get("new_failed", {}))),
        ]
        if verdict.get("empty"):
            out.append("- **no tests ran in the gate run**")
        for title, items in (
            ("Missing from the gate run", verdict.get("missing", [])),
            ("Did not pass", ["%s [%s]" % kv for kv in sorted(verdict.get("not_passed", {}).items())]),
            ("New tests that failed", ["%s [%s]" % kv for kv in sorted(verdict.get("new_failed", {}).items())]),
        ):
            if items:
                out += ["", "%s:" % title]
                out += _bullets(items)
        out.append("")

    out += [
        "The owner decision is the separate `owner-approval` job for head commit "
        "%s." % md_code(head_sha or "unknown", 64),
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--assemble", help="JSON report written by assemble.py")
    ap.add_argument("--verdict", help="JSON verdict written by verdict.py")
    ap.add_argument("--head-sha", default="")
    ap.add_argument("--base-sha", default="")
    args = ap.parse_args(argv)
    sys.stdout.write(render(_load(args.assemble), _load(args.verdict), args.head_sha, args.base_sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
